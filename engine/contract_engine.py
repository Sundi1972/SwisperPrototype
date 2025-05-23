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
from engine.haystack_engine import get_haystack_pipeline
from haystack import Document

class ContractStateMachine:
    def __init__(self, template_path, schema_path=None):
        self.template_path = template_path
        self.schema_path = schema_path or "schemas/purchase_item.schema.json"
        self.verbose = self.load_verbosity_from_config()
        self.contract = self.load_template()
        self.state = "start"
        self.haystack_pipeline = get_haystack_pipeline()

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
            # Clear previous documents from the store
            self.haystack_pipeline.get_document_store().delete_documents()

            raw_results = search_product(parameters.get("product"))
            print(f"🔍 Found {len(raw_results)} products from external API")

            if not raw_results:
                contract["status"] = "failed"
                contract.setdefault("subtasks", []).append({
                    "id": "search_product", "type": "search", "status": "failed", "results": []
                })
                return {"status": "failed", "message": "No products found."}

            # Convert raw results to Haystack Documents
            haystack_documents = []
            for product_dict in raw_results:
                # Ensure all essential fields for content are present and are strings
                name = str(product_dict.get("name", ""))
                description = str(product_dict.get("description", ""))
                # Construct content string carefully
                content_parts = [name, description]
                # Add other relevant text fields if they exist
                if "snippet" in product_dict: # Example, adjust based on actual product_dict structure
                    content_parts.append(str(product_dict["snippet"]))
                
                content_str = " | ".join(filter(None, content_parts)) # Join non-empty strings

                # Meta should contain all original fields for later use
                meta_data = product_dict.copy()
                # Ensure basic fields required by later states are present in meta, even if None
                meta_data.setdefault("price", None)
                meta_data.setdefault("rating", 0) # Default rating to 0 if not present
                meta_data.setdefault("product_id", None)
                meta_data.setdefault("vendor", "unknown")
                meta_data.setdefault("name", name) # Ensure name is in meta as well

                haystack_documents.append(Document(content=content_str, meta=meta_data))
            
            # Write documents to the Haystack document store
            self.haystack_pipeline.get_document_store().write_documents(haystack_documents)
            
            # Run the Haystack pipeline
            # Adjust top_k as needed for Retriever and Ranker
            pipeline_results = self.haystack_pipeline.run(
                query=parameters.get("product"),
                params={"BM25Retriever": {"top_k": 10}, "SentenceTransformersRanker": {"top_k": 5}}
            )
            
            self.search_results = pipeline_results["documents"] # These are ranked Haystack Document objects
            
            print(f"🔍 Haystack processed {len(self.search_results)} products after ranking")

            contract.setdefault("subtasks", []).append({
                "id": "search_product",
                "type": "search",
                "status": "completed",
                # Storing raw results might be too verbose, consider storing only IDs or names
                "results_from_api_count": len(raw_results),
                "results_from_haystack_count": len(self.search_results)
            })

            if not self.search_results:
                contract["status"] = "failed" # Or handle differently, e.g., broaden search
                return {"status": "failed", "message": "No products found after Haystack processing."}

            # analyze_product_differences needs to be adapted for Haystack Documents
            # For now, we'll assume it can handle a list of Document objects or we adapt it later
            # For example, by passing [doc.meta for doc in self.search_results]
            product_metas_for_diff = [doc.meta for doc in self.search_results]

            if len(self.search_results) > 4: # Or some other threshold
                print("❓ Too many results, asking for preferences...")
                self.state = "clarify_preferences"
                return {"ask_user": analyze_product_differences(product_metas_for_diff)}
            else:
                print("✅ Few results, skipping preference clarification.")
                self.state = "filter"
                return self.next()

        elif self.state == "clarify_preferences":
            preferences = parameters.get("preferences", [])
            # Assuming self.search_results are Haystack Documents, extract meta for analysis
            product_metas_for_diff = [doc.meta for doc in self.search_results]

            if not preferences and user_input:
                print(f"📥 Received user preferences: {user_input}")
                preferences = analyze_user_preferences(product_metas_for_diff, user_input)
                contract["parameters"]["preferences"] = preferences

            if not preferences:
                print("❌ No preferences provided yet — re-asking user")
                return {"ask_user": analyze_product_differences(product_metas_for_diff)}

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

            # filter_products_with_llm expects a list of product dicts.
            # self.search_results is now a list of Haystack Documents.
            # We need to pass the meta data of these documents to the LLM function.
            product_metas_for_filtering = [doc.meta for doc in self.search_results]
            
            print(f"🔎 Filtering {len(product_metas_for_filtering)} products by preferences {preferences} before LLM")
            
            # filter_products_with_llm is expected to return a list of product dicts (the filtered ones)
            filtered_product_metas = filter_products_with_llm(product_metas_for_filtering, preferences)
            print(f"🔎 LLM filtered down to {len(filtered_product_metas)} products.")

            # Reconstruct Haystack Document list from the filtered metas
            # This requires matching filtered metas back to original Haystack documents
            # to preserve content and other Haystack-specific attributes.
            # A simple way is to use a unique ID if available, e.g. product_id.
            # Assuming 'product_id' is a unique identifier in meta.
            
            filtered_s_results_map = {doc.meta.get("product_id"): doc for doc in self.search_results if doc.meta.get("product_id")}
            
            filtered_documents = []
            if filtered_s_results_map: # only if product_id is reliable
                for meta in filtered_product_metas:
                    doc = filtered_s_results_map.get(meta.get("product_id"))
                    if doc:
                         # Update meta if LLM modified it (e.g. added a reason field)
                        doc.meta.update(meta)
                        filtered_documents.append(doc)
            else: # Fallback if product_id is not reliable: re-create documents, losing original content if not in meta
                 filtered_documents = [Document(content=meta.get("name",""), meta=meta) for meta in filtered_product_metas]


            if must_match:
                keyword = parameters.get("product", "").replace(" ", "").lower()
                # Filter based on name in meta
                filtered_documents = [doc for doc in filtered_documents if keyword in (doc.meta.get("name") or "").replace(" ", "").lower()]
            
            print(f"🔎 After 'must_match' and LLM filtering, {len(filtered_documents)} products remain.")

            if not filtered_documents:
                # Fallback logic: use top N from self.search_results (which are Haystack Documents)
                fallback_documents = self.search_results[:4] 
                print(f"⚠️ No filtered results, falling back to top {len(fallback_documents)} Haystack documents.")
                contract["subtasks"].append({
                    "id": "filter_results",
                    "type": "filter",
                    "status": "fallback",
                    "filtered_results_count": len(fallback_documents),
                    # Potentially log IDs or names if too verbose to store full docs
                    "filtered_results_preview": [d.meta.get("name") for d in fallback_documents] 
                })
                self.filtered_results = fallback_documents
            else:
                contract["subtasks"].append({
                    "id": "filter_results",
                    "type": "filter",
                    "status": "completed",
                    "filtered_results_count": len(filtered_documents),
                    "filtered_results_preview": [d.meta.get("name") for d in filtered_documents]
                })
                self.filtered_results = filtered_documents

            self.state = "check_compatibility"
            return self.next()

        elif self.state == "check_compatibility":
            constraints = parameters.get("constraints", {})
            # check_product_compatibility expects a list of product dicts.
            # self.filtered_results is a list of Haystack Documents.
            product_metas_for_compatibility = [doc.meta for doc in self.filtered_results]
            compatibility = check_product_compatibility(product_metas_for_compatibility, constraints)
            contract["subtasks"].append({
                "id": "check_compatibility",
                "type": "reasoning",
                "status": "completed",
                "compatibility": compatibility
            })
            self.state = "rank_and_select"
            return self.next()

        elif self.state == "rank_and_select":
            # self.filtered_results is a list of Haystack Document objects.
            # The rank_and_select method is updated to handle this.
            best_product_dict = self.rank_and_select(self.filtered_results, parameters.get("preferences"))
            contract["subtasks"].append({
                "id": "select_product",
                "type": "rank_and_select",
                "status": "completed",
                "output": best_product_dict # This is already a dict
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

    def rank_and_select(self, filtered_haystack_documents, preferences=None):
        # filtered_haystack_documents is a list of Haystack Document objects.
        if not filtered_haystack_documents:
            return {
                "vendor": "unknown",
                "price": None,
                "product_id": None,
                "name": "N/A",
                "reason": "No matching products found after filtering."
            }

        # The scoring function now accesses attributes from doc.meta
        def score(doc):
            price = doc.meta.get("price")
            # Ensure price is a number, default to infinity if not (for minimization)
            if not isinstance(price, (int, float)):
                price = float("inf")
            
            rating = doc.meta.get("rating")
            # Ensure rating is a number, default to 0 if not
            if not isinstance(rating, (int, float)):
                rating = 0
                
            return (rating, -price) # Higher rating is better, lower price is better

        # Sort documents based on score
        # The list contains Haystack Document objects.
        sorted_documents = sorted(filtered_haystack_documents, key=score, reverse=True)
        
        # The best product is the first Document object in the sorted list.
        # We need to return its meta dictionary, as expected by the rest of the FSM.
        best_product_meta = sorted_documents[0].meta
        
        # Ensure the returned dictionary has a 'reason' if it's not already there.
        best_product_meta.setdefault("reason", "Selected as best match based on rating and price.")
        
        return best_product_meta

    def save_final_contract(self, filename="final_contract.json"):
        self.contract["created_at"] = datetime.now().isoformat()
        with open(filename, "w") as f:
            json.dump(self.contract, f, indent=2)