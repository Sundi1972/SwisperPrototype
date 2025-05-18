import logging
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Dict, Any
from openai import OpenAI
import json
from fastapi.middleware.cors import CORSMiddleware
from engine.contract_engine import ContractStateMachine  # Updated filename
import shelve
import atexit

# --- Logging configuration ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],  # Frontend origin
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
client = OpenAI()

class Message(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[Message]
    session_id: str = "default"

# Persistent session store using shelve
sessions = shelve.open("swisper_sessions.db", writeback=True)
atexit.register(lambda: sessions.close())

def get_engine(session_id: str) -> ContractStateMachine:
    if session_id not in sessions:
        logging.info(f"🆕 Creating new engine for session: {session_id}")
        engine = ContractStateMachine(
            template_path="contract_templates/purchase_item.yaml",
            schema_path="schemas/purchase_item.schema.json"
        )
        sessions[session_id] = engine
    else:
        logging.info(f"🔄 Reusing engine for session: {session_id} (state: {sessions[session_id].state})")
    return sessions[session_id]

def run_gpt(messages: List[Dict[str, str]], session_id: str) -> Dict:
    logging.info(f"Handling run_gpt for session: {session_id} with {len(messages)} messages")
    engine = get_engine(session_id)

    # 💡 If not in start state, use latest user input to continue contract
    if engine.state != "start":
        logging.info(f"🔁 Continuing contract for session: {session_id} in state: {engine.state}")
        user_message = messages[-1]["content"]
        result = engine.next(user_input=user_message)
        if "ask_user" in result:
            return {"reply": result["ask_user"], "session_id": session_id}
        elif result.get("status") == "completed":
            engine.save_final_contract("final_contract.json")
            summary = result["contract"].get("subtasks", [])[-2]["output"]
            return {
                "reply": f"✅ Product selected: {summary['name']} ({summary['price']} CHF, {summary['rating']}★)",
                "session_id": session_id
            }

    # 🧠 Otherwise use GPT function call to start contract
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=messages,
        tools=[{
            "type": "function",
            "function": {
                "name": "run_purchase_contract",
                "description": "Starts or continues the purchase contract state machine",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "product_name": {
                            "type": "string",
                            "description": "The product to search for"
                        },
                        "session_id": {
                            "type": "string"
                        }
                    },
                    "required": ["product_name", "session_id"]
                }
            }
        }],
        tool_choice="auto"
    )

    message = response.choices[0].message

    if hasattr(message, "tool_calls") and message.tool_calls:
        tool_call = message.tool_calls[0]
        if tool_call.function.name == "run_purchase_contract":
            args = tool_call.function.arguments
            if isinstance(args, str):
                args = json.loads(args)

            session_id = args.get("session_id", "default")
            engine = get_engine(session_id)

            if engine.state == "start":
                engine.fill_parameters({
                    "product": args.get("product_name"),
                    "price_limit": 400,
                    "delivery_by": "2024-09-11",
                    "preferences": ["low noise", "high performance", "power efficiency"],
                    "must_match_model": True,
                    "constraints": {
                        "motherboard compatibility": "MSI MAG B850 Tomahawk Max WIFI"
                    }
                })

            result = engine.next()

            if "ask_user" in result:
                return {"reply": result["ask_user"], "session_id": session_id}
            elif result.get("status") == "completed":
                engine.save_final_contract("final_contract.json")
                summary = result["contract"].get("subtasks", [])[-2]["output"]
                return {
                    "reply": f"✅ Product selected: {summary['name']} ({summary['price']} CHF, {summary['rating']}★)",
                    "session_id": session_id
                }

    return {"reply": getattr(message, "content", None) or "Sorry, I couldn’t help with that.", "session_id": session_id}

@app.post("/swisper/chat")
async def swisper_chat(payload: ChatRequest):
    logging.info(f"📩 Incoming request: session_id={payload.session_id}")
    messages = [message.model_dump() for message in payload.messages]
    reply = run_gpt(messages, session_id=payload.session_id)
    logging.info(f"💬 Reply for session {payload.session_id}: {reply.get('reply')[:100]}")
    return reply