import yaml
import json
from pathlib import Path
from datetime import datetime
from jsonschema import validate
from tools.google_shopping_api import search_google_shopping as search_product
from engine.llm_helpers import (
    analyze_product_differences,
    analyze_user_preferences,
    check_product_compatibility,
    filter_products_with_llm
)

class ContractStateMachine:
    def __init__(self, template_path, schema_path=None):
        self.template_path = template_path
        self.schema_path = schema_path or "schemas/purchase_item.schema.json"
        self.verbose = self.load_verbosity_from_config()
        self.contract = self.load_template()
        self.state = "start"

    def load_verbosity_from_config(self):
        config_path = Path("config.json")
        if config_path.exists():
            try:
                with open(config_path, 'r') as f:
                    config = json.load(f)
                    return config.get("verbose", False)
            except Exception:
                pass
        return False

    def load_template(self):
        with open(self.template_path, 'r') as f:
            return yaml.safe_load(f)

    def fill_parameters(self, param_data):
        self.contract["parameters"] = self.contract.get("parameters", {})
        self.contract["parameters"].update(param_data)

    def next(self, user_input=None):
        contract = self.contract
        parameters = contract.get("parameters", {})

        print(f"🧭 Current state: {self.state}")

        if self.state == "start":
            print("🚦 Transition: start → search")
            self.state = "search"
            return self.next()

        elif self.state == "search":
            results = search_product(parameters.get("product"))
            print(f"🔍 Found {len(results)} products")
            contract.setdefault("subtasks", []).append({
                "id": "search_product",
                "type": "search",
                "status": "completed",
                "results": results
            })
            self.search_results = results

            if not results:
                contract["status"] = "failed"
                return {"status": "failed", "message": "No products found."}

            if len(results) > 4:
                print("❓ Too many results, asking for preferences...")
                self.state = "clarify_preferences"
                return {"ask_user": analyze_product_differences(results)}
            else:
                print("✅ Few results, skipping preference clarification.")
                self.state = "filter"
                return self.next()

        elif self.state == "clarify_preferences":
            preferences = parameters.get("preferences", [])
            if not preferences and user_input:
                print(f"📥 Received user preferences: {user_input}")
                preferences = analyze_user_preferences(self.search_results, user_input)
                contract["parameters"]["preferences"] = preferences

            if not preferences:
                print("❌ No preferences provided yet — re-asking user")
                return {"ask_user": analyze_product_differences(self.search_results)}

            contract["subtasks"].append({
                "id": "clarify_preferences",
                "type": "ask_user",
                "prompt": "What features matter most to you?",
                "status": "completed",
                "response": ", ".join(preferences)
            })

            self.state = "filter"
            return self.next()

        elif self.state == "filter":
            preferences = parameters.get("preferences", [])
            must_match = parameters.get("must_match_model", False)
            filtered = filter_products_with_llm(self.search_results, preferences)

            print(f"🔎 Filtering {len(self.search_results)} products by preferences {preferences}")

            if must_match:
                keyword = parameters.get("product", "").replace(" ", "").lower()
                filtered = [p for p in filtered if keyword in (p.get("name") or "").replace(" ", "").lower()]

            if not filtered:
                fallback = self.search_results[:4]
                print("⚠️ No filtered results, falling back to top 4.")
                contract["subtasks"].append({
                    "id": "filter_results",
                    "type": "filter",
                    "status": "fallback",
                    "filtered_results": fallback
                })
                self.filtered_results = fallback
            else:
                contract["subtasks"].append({
                    "id": "filter_results",
                    "type": "filter",
                    "status": "completed",
                    "filtered_results": filtered
                })
                self.filtered_results = filtered

            self.state = "check_compatibility"
            return self.next()

        elif self.state == "check_compatibility":
            constraints = parameters.get("constraints", {})
            compatibility = check_product_compatibility(self.filtered_results, constraints)
            contract["subtasks"].append({
                "id": "check_compatibility",
                "type": "reasoning",
                "status": "completed",
                "compatibility": compatibility
            })
            self.state = "rank_and_select"
            return self.next()

        elif self.state == "rank_and_select":
            best = self.rank_and_select(self.filtered_results, parameters.get("preferences"))
            contract["subtasks"].append({
                "id": "select_product",
                "type": "rank_and_select",
                "status": "completed",
                "output": best
            })
            self.state = "confirm_order"
            return {"ask_user": "Shall I go ahead and buy this product?"}

        elif self.state == "confirm_order":
            contract["subtasks"].append({
                "id": "confirm_order",
                "type": "ask_user",
                "prompt": "Confirm product purchase?",
                "status": "completed",
                "response": "confirmed"
            })
            self.state = "checkout"
            return self.next()

        elif self.state == "checkout":
            contract["subtasks"].append({
                "id": "place_order",
                "type": "checkout",
                "status": "completed"
            })
            contract["order_confirmed"] = True
            contract["status"] = "completed"
            contract["created_at"] = datetime.now().isoformat()
            self.state = "completed"
            return {"status": "completed", "contract": contract}

    def rank_and_select(self, filtered_products, preferences=None):
        if not filtered_products:
            return {
                "vendor": "unknown",
                "price": None,
                "product_id": None,
                "reason": "No matching products found"
            }

        def score(p):
            return ((p.get("rating") or 0), -(p.get("price") or float("inf")))

        return sorted(filtered_products, key=score, reverse=True)[0]

    def save_final_contract(self, filename="final_contract.json"):
        self.contract["created_at"] = datetime.now().isoformat()
        with open(filename, "w") as f:
            json.dump(self.contract, f, indent=2)