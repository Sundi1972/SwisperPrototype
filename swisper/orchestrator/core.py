import re
import os
import logging
from typing import List, Dict, Any, Optional
from openai import AsyncOpenAI 
from pydantic import BaseModel 
import datetime 
import json 

# Import Haystack pipeline creation function for contract path
try:
    from contract_engine.contract_pipeline import create_product_selection_pipeline
except ImportError: 
    from swisper.contract_engine.contract_pipeline import create_product_selection_pipeline

# Import RAG function
try:
    from haystack_pipeline import ask_doc as ask_document_pipeline
    RAG_AVAILABLE = True
    logging.getLogger(__name__).info("RAG `ask_doc` function imported successfully.")
except ImportError:
    logging.getLogger(__name__).warning("Failed to import `ask_doc` from `haystack_pipeline`. RAG functionality will be disabled.")
    RAG_AVAILABLE = False
    # Define a dummy function if import fails, so the rest of the code doesn't break
    def ask_document_pipeline(question: str): 
        return "RAG system is currently unavailable due to an import error."

# Import session store functions
from . import session_store 
from .session_store import set_pending_confirmation, get_pending_confirmation, clear_pending_confirmation

logger = logging.getLogger(__name__)

# Initialize OpenAI client (for chat path)
try:
    async_client = AsyncOpenAI()
    if not os.environ.get("OPENAI_API_KEY"):
        logger.warning("OPENAI_API_KEY not found. LLM calls for chat/RAG path may fail.")
except Exception as e:
    logger.error(f"Failed to initialize AsyncOpenAI client: {e}", exc_info=True)
    async_client = None

# Initialize Product Selection Pipeline (Contract Path)
try:
    PRODUCT_SELECTION_PIPELINE = create_product_selection_pipeline()
    logger.info("Product Selection Pipeline initialized successfully.")
except Exception as e:
    logger.error(f"Failed to initialize Product Selection Pipeline: {e}", exc_info=True)
    PRODUCT_SELECTION_PIPELINE = None

class Message(BaseModel): 
    role: str
    content: str

async def handle(messages: List[Message], session_id: str) -> Dict[str, Any]:
    logger.info(f"Orchestrator handling for session: {session_id}, with {len(messages)} messages.")
    
    if not messages:
        logger.warning(f"Orchestrator received empty messages list for session: {session_id}")
        return {"reply": "No messages provided to orchestrator.", "session_id": session_id}

    last_user_message_pydantic = messages[-1] 
    last_user_message_content = last_user_message_pydantic.content
    
    session_store.add_chat_message(session_id, last_user_message_pydantic.model_dump())

    reply_content = "" # Initialize reply_content

    # 1. Check for a pending confirmation (from contract path)
    pending_product = get_pending_confirmation(session_id)
    if pending_product:
        product_name = pending_product.get("name", "the selected product")
        if last_user_message_content.lower() in ["yes", "y", "confirm", "ok", "okay", "proceed", "sure"]:
            reply_content = f"Great! Order confirmed for {product_name}."
            logger.info(f"Session {session_id}: User confirmed order for {product_name}.")
            try:
                artifact_dir = "tmp/contracts"
                os.makedirs(artifact_dir, exist_ok=True)
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_session_id = re.sub(r'[^a-zA-Z0-9_-]', '_', session_id) 
                artifact_path = os.path.join(artifact_dir, f"{safe_session_id}_{timestamp}.json")
                artifact_data = {
                    "session_id": session_id, "confirmed_product": pending_product,
                    "confirmation_time": datetime.datetime.now().isoformat(),
                    "chat_history_at_confirmation": session_store.get_chat_history(session_id) 
                }
                with open(artifact_path, "w") as f: json.dump(artifact_data, f, indent=2)
                logger.info(f"Session {session_id}: Contract artifact saved to {artifact_path}")
            except Exception as e:
                logger.error(f"Session {session_id}: Failed to save contract artifact: {e}", exc_info=True)
            clear_pending_confirmation(session_id)
        elif last_user_message_content.lower() in ["no", "n", "cancel", "stop"]:
            reply_content = f"Okay, the order for {product_name} has been cancelled."
            logger.info(f"Session {session_id}: User cancelled order for {product_name}.")
            clear_pending_confirmation(session_id)
        else: 
            reply_content = f"Sorry, I didn't quite understand. For {product_name}, please confirm with 'yes' or 'no'."
        
        # This return is inside the 'if pending_product:' block
        if reply_content: # Ensure reply_content was set
             session_store.add_chat_message(session_id, {"role": "assistant", "content": reply_content})
        session_store.save_session(session_id)
        return {"reply": reply_content, "session_id": session_id}

    # 2. If no pending confirmation, proceed with routing: Contract, RAG, or Chat
    contract_keywords = r"\b(buy|purchase|order|acquire|get me|shop for|find a|buy an)\b"
    is_contract_intent = bool(PRODUCT_SELECTION_PIPELINE and re.search(contract_keywords, last_user_message_content, re.IGNORECASE))
    
    rag_trigger_keyword = "#rag" # Note: conceptual code had "#rag " (with space), this is more flexible
    is_rag_intent = bool(RAG_AVAILABLE and last_user_message_content.lower().startswith(rag_trigger_keyword))

    if is_contract_intent:
        logger.info(f"Contract path triggered for session {session_id}. Input: '{last_user_message_content}'")
        try:
            # The query for the pipeline is the user message itself (or a processed version if needed)
            pipeline_result = PRODUCT_SELECTION_PIPELINE.run(query=last_user_message_content)
            selected_product_node_output = pipeline_result.get("ProductSelector", ({},'')) 
            selected_product_data = selected_product_node_output[0] 
            selected_product = selected_product_data.get("selected_product")

            if selected_product and selected_product.get("name"): 
                set_pending_confirmation(session_id, selected_product)
                product_name = selected_product.get("name")
                product_price = selected_product.get("price", "price not available")
                reply_content = f"I found this product: {product_name} (Price: {product_price}). Would you like to confirm this order? (yes/no)"
            else:
                logger.warning(f"Pipeline did not select a product for session {session_id}. Query: '{last_user_message_content}'. Output: {pipeline_result}")
                reply_content = "Sorry, I couldn't find a suitable product for your query. Could you try rephrasing or a different product?"
        except Exception as e:
            logger.error(f"Error running ProductSelectionPipeline for session {session_id}: {e}", exc_info=True)
            reply_content = "Sorry, there was an error trying to find products for you."
    
    elif is_rag_intent: # RAG Path
        logger.info(f"RAG path for session {session_id}. Input: '{last_user_message_content}'")
        question_for_rag = last_user_message_content[len(rag_trigger_keyword):].lstrip()
        
        if not question_for_rag:
            reply_content = "Please provide a question after the #rag trigger."
        else:
            try:
                # ask_doc is currently synchronous.
                reply_content = ask_document_pipeline(question=question_for_rag)
                logger.info(f"RAG pipeline returned for session {session_id}: '{reply_content[:100]}...'")
            except Exception as e: 
                logger.error(f"Error calling RAG ask_document_pipeline for session {session_id}: {e}", exc_info=True)
                reply_content = "Sorry, there was an error trying to answer your document question."
    
    else: # General Chat Path
        logger.info(f"Chat path for session {session_id}. Input: '{last_user_message_content}'")
        if not async_client:
            logger.error("AsyncOpenAI client not available for chat path.")
            reply_content = "Error: LLM service not available." 
        else:
            current_chat_history = session_store.get_chat_history(session_id)
            try:
                llm_response = await async_client.chat.completions.create(model="gpt-4o", messages=current_chat_history)
                reply_content = llm_response.choices[0].message.content
            except Exception as e:
                logger.error(f"OpenAI API call failed for session {session_id}: {e}", exc_info=True)
                reply_content = "Sorry, an error occurred with the AI assistant."

    # Fallback reply if no path explicitly set it (should be rare given the logic structure)
    if not reply_content: 
        logger.error(f"Orchestrator did not produce a reply for session {session_id}. This indicates a logic gap.")
        reply_content = "I'm not sure how to respond to that. Please try again."

    session_store.add_chat_message(session_id, {"role": "assistant", "content": reply_content})
    session_store.save_session(session_id)
    return {"reply": reply_content, "session_id": session_id}
