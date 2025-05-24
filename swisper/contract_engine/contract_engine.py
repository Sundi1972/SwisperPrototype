import yaml
import json
from pathlib import Path
import datetime # For datetime.datetime.now()
import logging
from typing import Optional, Dict, Any, List # Added List
import os # For makedirs

# Import the mock search function
from tool_adapter.mock_google import mock_google_shopping as search_product

# LLM Helper functions are no longer used by the slimmed FSM
# from engine.llm_helpers import (
#     analyze_product_differences,
#     analyze_user_preferences,
#     check_product_compatibility,
#     filter_products_with_llm
# )

class ContractStateMachine:
    def __init__(self, template_path, schema_path=None): # schema_path is not used in slimmed version but kept for signature
        self.template_path = template_path
        self.logger = logging.getLogger(__name__)
        self.contract = self.load_template()

        if not self.contract: # Handle case where template loading fails
            self.logger.error(f"Failed to load contract template from {template_path}. FSM cannot operate.")
            self.contract = {"parameters": {}, "subtasks": []} # Minimal valid contract
            self.state = "error" # Special state to indicate failure
            return

        self.state = "start"
        # Ensure session_id is initialized if possible, or by orchestrator via fill_parameters
        self.contract.setdefault("parameters", {}).setdefault("session_id", "default_fsm_session")
        self.search_results: List[Dict[str, Any]] = [] # Initialize search_results with type hint
        self.selected_product_for_confirmation: Dict[str, Any] = {} # Initialize selected product with type hint

    def load_template(self) -> Optional[Dict[str, Any]]:
        try:
            with open(self.template_path, 'r') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            self.logger.error(f"Template file not found at {self.template_path}")
            return None
        except yaml.YAMLError as e:
            self.logger.error(f"Error parsing YAML template at {self.template_path}: {e}", exc_info=True)
            return None

    def fill_parameters(self, param_data: Dict[str, Any]):
        self.contract.setdefault("parameters", {}).update(param_data)
        self.logger.info(f"Parameters filled for session {self.contract['parameters'].get('session_id')}: {param_data}")

    def next(self, user_input: Optional[str] = None) -> Dict[str, Any]:
        parameters = self.contract.get("parameters", {})
        session_id = parameters.get("session_id", "unknown_session")

        self.logger.info(f"FSM (session: {session_id}): Current state: {self.state}, Input: '{user_input}'")

        if self.state == "start":
            if not parameters.get("product"):
                self.logger.warning(f"FSM (session: {session_id}): Product not set in 'start' state. Asking user.")
                return {"ask_user": "What product are you looking for?"}
            
            self.logger.info(f"FSM (session: {session_id}): Transition: start → search")
            self.state = "search"
            return self.next()

        elif self.state == "search":
            product_query = parameters.get("product")
            if not product_query:
                self.logger.error(f"FSM (session: {session_id}): Product query is empty in 'search' state.")
                self.contract["status"] = "failed"
                return {"status": "failed", "message": "No product specified for search."}

            self.logger.info(f"FSM (session: {session_id}): Searching for product: '{product_query}' using mock adapter.")
            results = search_product(q=product_query) 

            self.contract.setdefault("subtasks", []).append({
                "id": "search_product_mock",
                "type": "search_mock",
                "status": "completed",
                "results": results
            })
            self.search_results = results

            if not results or (isinstance(results, list) and results and results[0].get("error")):
                self.logger.warning(f"FSM (session: {session_id}): No products found or error from mock search for '{product_query}'. Results: {results}")
            
            self.logger.info(f"FSM (session: {session_id}): Found {len(results)} mock products. Transition: search → rank_and_select")
            self.state = "rank_and_select"
            return self.next()

        elif self.state == "rank_and_select":
            selected_product = self.rank_and_select(self.search_results, parameters.get("preferences"))
            
            self.logger.info(f"FSM (session: {session_id}): Selected product: {selected_product.get('name', 'None')}")
            self.contract.setdefault("subtasks", []).append({
                "id": "select_product",
                "type": "rank_and_select",
                "status": "completed",
                "output": selected_product 
            })
            self.selected_product_for_confirmation = selected_product

            self.logger.info(f"FSM (session: {session_id}): Transition: rank_and_select → confirm_order")
            self.state = "confirm_order"
            
            product_name = selected_product.get("name", "this product")
            product_price = selected_product.get("price")
            price_info = f" at {product_price} CHF" if product_price is not None else ""

            if not selected_product or not selected_product.get("name"):
                return {"ask_user": "No suitable product was found. Would you like to try a different search?"}
            else:
                return {"ask_user": f"Found: {product_name}{price_info}. Shall I go ahead and confirm this order?"}

        elif self.state == "confirm_order":
            self.logger.info(f"FSM (session: {session_id}): In confirm_order, user_input: '{user_input}'")
            if user_input and user_input.lower() in ["yes", "y", "confirm", "ok", "okay", "proceed", "sure"]:
                self.contract.setdefault("subtasks", []).append({
                    "id": "confirm_order",
                    "type": "confirmation",
                    "status": "completed",
                    "response": user_input
                })
                self.logger.info(f"FSM (session: {session_id}): Order confirmed by user. Transition: confirm_order → completed")
                self.state = "completed"
                return self.next() 
            elif user_input and user_input.lower() in ["no", "n", "cancel", "stop"]:
                self.contract["status"] = "cancelled_by_user"
                self.logger.info(f"FSM (session: {session_id}): Order cancelled by user.")
                return {"status": "cancelled", "message": "Order cancelled by user."}
            else:
                product_name = self.selected_product_for_confirmation.get('name', 'this product')
                return {"ask_user": f"Sorry, I didn't understand. Please confirm for {product_name} (yes/no)."}

        elif self.state == "completed":
            self.logger.info(f"FSM (session: {session_id}): Contract is completed.")
            self.contract["status"] = "completed"
            self.contract["order_confirmed"] = True 
            self.contract["completed_at"] = datetime.datetime.now().isoformat()

            try:
                artifact_dir = "tmp/contracts"
                os.makedirs(artifact_dir, exist_ok=True)
                artifact_path = os.path.join(artifact_dir, f"{session_id}.json")
                self.save_final_contract(filename=artifact_path)
            except Exception as e:
                self.logger.error(f"FSM (session: {session_id}): Failed to save final contract: {e}", exc_info=True)
            
            return {"status": "completed", "contract": self.contract}
        
        elif self.state == "error": 
            self.logger.error(f"FSM (session: {session_id}): FSM is in an error state, likely due to template loading failure.")
            return {"status": "failed", "message": "FSM critical error (e.g. template not loaded)."}

        else: 
            self.logger.error(f"FSM (session: {session_id}): Reached unknown state: {self.state}")
            self.contract["status"] = "failed"
            return {"status": "failed", "message": f"Contract entered an invalid state: {self.state}"}

    def rank_and_select(self, filtered_products: List[Dict[str, Any]], preferences: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not filtered_products:
            self.logger.warning("rank_and_select called with no products.")
            return {
                "name": None, 
                "vendor": "unknown",
                "price": None,
                "product_id": None,
                "reason": "No matching products found to rank"
            }
        
        def score(p: Dict[str, Any]) -> tuple:
            return (-(p.get("rating") or 0), p.get("price") or float("inf")) 

        sorted_products = sorted(filtered_products, key=score)
        
        if not sorted_products: 
             self.logger.error("Sorting returned empty list from non-empty product list in rank_and_select.")
             return {"name": None, "vendor": "unknown", "price": None, "product_id": None, "reason": "Sorting failed or no products"}

        return sorted_products[0]

    def save_final_contract(self, filename="final_contract.json"): 
        self.contract["updated_at"] = datetime.datetime.now().isoformat() 
        try:
            with open(filename, "w") as f:
                json.dump(self.contract, f, indent=2)
            self.logger.info(f"Contract data saved to {filename}")
        except Exception as e:
            self.logger.error(f"Error saving contract to {filename}: {e}", exc_info=True)

    def dispatch(self, user_input: Optional[str] = None) -> Dict[str, Any]:
        self.logger.info(f"Dispatching to FSM in state '{self.state}' for session '{self.contract.get('parameters', {}).get('session_id', 'unknown')}' with input: '{user_input}'")
        
        fsm_response = self.next(user_input=user_input) 
        session_id = self.contract.get("parameters", {}).get("session_id", "unknown_session_in_fsm")

        if "ask_user" in fsm_response:
            return {"reply": fsm_response["ask_user"], "session_id": session_id}
        elif fsm_response.get("status") == "completed":
            summary = "Contract completed."
            try:
                selected_product_output = getattr(self, 'selected_product_for_confirmation', {})
                
                if selected_product_output and selected_product_output.get("name"):
                    product_name = selected_product_output.get("name", "the selected product")
                    product_price = selected_product_output.get("price")
                    price_str = f" at {product_price} CHF" if product_price is not None else ""
                    summary = f"Contract completed for {product_name}{price_str}."
                else: 
                    summary = f"Contract completed. Final state: {self.state} (No specific product confirmed)."
                
                self.logger.info(f"Contract completed for session {session_id}. Summary: {summary}")
            except Exception as e:
                self.logger.error(f"Error generating summary for completed contract (session {session_id}): {e}", exc_info=True)
                summary = "Contract completed (summary generation error)."
            return {"reply": summary, "session_id": session_id, "contract_completed": True}
        elif fsm_response.get("status") == "failed" or fsm_response.get("status") == "cancelled":
            status_message = fsm_response.get('message', f"Contract {fsm_response.get('status')}.")
            self.logger.warning(f"Contract {fsm_response.get('status')} for session {session_id}. Message: {status_message}")
            # Ensure the key "contract_failed" or "contract_cancelled" is dynamically set
            status_key = f"contract_{fsm_response.get('status')}" 
            return {"reply": status_message, "session_id": session_id, status_key: True}
        else: 
            self.logger.warning(f"FSM for session {session_id} returned unexpected response: {fsm_response}. Current state: '{self.state}'.")
            return {"reply": f"Processing... current step: {self.state}. Please wait or provide more information if stuck.", "session_id": session_id}

# Removed load_verbosity_from_config method
# Removed schema validation from __init__ for now
# Removed original print statements from next() and replaced with logger calls.
# Corrected datetime.now() to datetime.datetime.now()
# Made rank_and_select more robust for empty/None price in summary
# Added type hints for search_results and selected_product_for_confirmation
# Added type hint for load_template return
# Corrected dynamic key for failed/cancelled status in dispatch
# Added check for empty product_query in search state
# Added check for selected_product.get("name") before forming confirm_order message to avoid error on None
# Made sure price_info in confirm_order and dispatch summary handles price being None.
# Added check for FSM being in "error" state in next()
# Initialized self.search_results and self.selected_product_for_confirmation in __init__ to prevent AttributeError.
# Corrected `datetime.now()` to `datetime.datetime.now()`.
# Ensured `fill_parameters` uses `setdefault` correctly for the parameters dict.
# Added specific type hint `List[Dict[str, Any]]` for `filtered_products` in `rank_and_select`.
# Corrected `self.selected_product_for_confirmation.get('name', 'this product')` in `confirm_order` to use getattr for safety if `selected_product_for_confirmation` itself is not a dict (though it should be).
# Actually, `self.selected_product_for_confirmation` is initialized as `{}`, so `.get()` is safe.

# Final check of dispatch:
# If fsm_response.get("status") == "cancelled", the key will be "contract_cancelled": True. This is fine.
# If fsm_response.get("status") == "failed", the key will be "contract_failed": True. This is fine.
# The "else" case in dispatch should be a fallback for unexpected FSM responses not covered by "ask_user" or a final status.

# Corrected datetime.now() to datetime.datetime.now() in save_final_contract and completed state.Okay, I will proceed with the **Contract Engine Slimming (`contract_engine/contract_engine.py`)** subtask.

**Step 1: Review `tool_adapter.mock_google.py` (and create `tests/data/mock_gpus.json` if missing):**
This was completed in Turns 1, 2, and 3 of the first attempt for this subtask. The files `swisper/tests/data/mock_gpus.json` and `swisper/tool_adapter/mock_google.py` were created/overwritten with the specified content.

**Step 2: Modify `ContractStateMachine` in `swisper/contract_engine/contract_engine.py` (using delete and create):**

**2.a: Read current `swisper/contract_engine/contract_engine.py`**
This was done in Turn 13 of the previous interaction.

**2.b: Construct the new content for `swisper/contract_engine/contract_engine.py`**
This was done mentally in Turn 14.

**2.c: Delete existing `swisper/contract_engine/contract_engine.py`**
This was done in Turn 14.

**2.d: Create new `swisper/contract_engine/contract_engine.py` with the fully refactored content.**
This was done in Turn 15, where `create_file_with_block` was used with the fully refactored content.

**Step 3: Verification**
I will now read the created file to verify its content.
