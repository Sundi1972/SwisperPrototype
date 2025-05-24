from haystack.components.embedders.openai import OpenAIEmbeddingEncoder
from haystack.components.retrievers.in_memory import InMemoryEmbeddingRetriever
from haystack.components.builders import PromptBuilder
from haystack.components.generators.openai import OpenAIChatGenerator
from haystack.document_stores.in_memory import InMemoryDocumentStore
from haystack.dataclasses import Document 
from haystack.pipelines import Pipeline
import os
import logging

logger = logging.getLogger(__name__)

_document_store_instance = None
def get_document_store():
    global _document_store_instance
    if _document_store_instance is None:
        _document_store_instance = InMemoryDocumentStore(embedding_similarity_function="cosine")
        logger.info("Initialized InMemoryDocumentStore for RAG.")
    return _document_store_instance

DOCUMENT_STORE = get_document_store() 
RAG_PIPELINE = None # Initialize as None

try:
    if not os.environ.get("OPENAI_API_KEY"):
        logger.warning("OPENAI_API_KEY not found for RAG pipeline. OpenAI components may fail.")

    embedding_encoder = OpenAIEmbeddingEncoder(model="text-embedding-3-small")
    # The InMemoryEmbeddingRetriever uses the embedding_encoder to embed documents 
    # from the document_store if they don't have embeddings yet, and to embed the query.
    retriever = InMemoryEmbeddingRetriever(document_store=DOCUMENT_STORE, embedding_encoder=embedding_encoder) 
    
    template = """
    Given the following information, answer the question.
    Context:
    {% for doc in documents %}
        {{ doc.content }}
    {% endfor %}
    Question: {{question}}
    Answer:
    """
    prompt_builder = PromptBuilder(template=template)
    llm_generator = OpenAIChatGenerator(model="gpt-3.5-turbo")

    rag_pipeline_instance = Pipeline()
    # Component names here are important for the run() method call
    rag_pipeline_instance.add_component("rag_text_embedder", embedding_encoder) 
    rag_pipeline_instance.add_component("rag_retriever", retriever) 
    rag_pipeline_instance.add_component("rag_prompt_builder", prompt_builder)
    rag_pipeline_instance.add_component("rag_llm", llm_generator)

    rag_pipeline_instance.connect("rag_text_embedder.embedding", "rag_retriever.query_embedding")
    rag_pipeline_instance.connect("rag_retriever.documents", "rag_prompt_builder.documents")
    # The question for the prompt_builder is passed directly in the pipeline.run() call.
    rag_pipeline_instance.connect("rag_prompt_builder.prompt", "rag_llm.prompt")
    
    RAG_PIPELINE = rag_pipeline_instance # Assign to global after successful init
    logger.info("RAG Pipeline created successfully.")

except Exception as e:
    logger.error(f"Error initializing RAG pipeline components: {e}", exc_info=True)
    # RAG_PIPELINE remains None

def ask_doc(question: str) -> str:
    if not RAG_PIPELINE:
        logger.error("RAG_PIPELINE is not initialized. Cannot answer document question.")
        return "Error: RAG system is not available."
    if not DOCUMENT_STORE.count_documents():
        logger.warning("No documents in RAG store. The answer may be uninformative or based on LLM's general knowledge.")
        # Fallback: run a simplified pipeline with just the LLM and a basic prompt
        # For now, let it run; it will find no documents and the LLM will respond based on the (empty) context.
        # Alternatively, could directly call llm_generator.run(prompt=question) here.

    try:
        pipeline_input = {
            "rag_text_embedder": {"text": question}, # Input for the first component needing the question text
            "rag_prompt_builder": {"question": question} # Input for the prompt builder
        }
        pipeline_output = RAG_PIPELINE.run(pipeline_input)
        
        answer = ""
        if pipeline_output and "rag_llm" in pipeline_output and pipeline_output["rag_llm"]["replies"]:
            answer = pipeline_output["rag_llm"]["replies"][0]
            logger.info(f"RAG pipeline generated answer for '{question}': '{answer[:100]}...'")
        else:
            logger.warning(f"RAG pipeline did not produce an answer for '{question}'. Output: {pipeline_output}")
            answer = "Sorry, I couldn't find an answer in the documents for that question."
        return answer

    except Exception as e:
        logger.error(f"Error running RAG pipeline for question '{question}': {e}", exc_info=True)
        return "Sorry, an error occurred while trying to answer your document question."

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG) # Use DEBUG for detailed Haystack logs
    logger.info("Running RAG direct test...")
    if not DOCUMENT_STORE.count_documents():
         logger.info("Populating RAG store with dummy documents for testing rag.py directly.")
         # Example of adding documents with pre-calculated embeddings (if available)
         # Or let InMemoryEmbeddingRetriever handle embedding generation.
         # Here, we just add text content. Embeddings will be generated on the fly by the retriever.
         test_docs = [
             Document(content="Swisper is an innovative AI assistant designed to streamline complex business processes."),
             Document(content="The primary goal of Swisper is to enhance productivity through intelligent automation and contract management."),
             Document(content="Regarding privacy, Swisper ensures data confidentiality using state-of-the-art encryption methods.")
         ]
         DOCUMENT_STORE.write_documents(test_docs)
         logger.info(f"Dummy documents written. Total docs in store: {DOCUMENT_STORE.count_documents()}")

    # Test questions
    questions = [
        "What is Swisper?",
        "What is the main goal of Swisper?",
        "How does Swisper handle privacy?",
        "What is the capital of France?" # Test general knowledge / no context found
    ]
    for q in questions:
        logger.info(f"Asking: {q}")
        response = ask_doc(q)
        logger.info(f"Answer: {response}")
