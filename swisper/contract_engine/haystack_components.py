from haystack.nodes import BaseComponent
from typing import List, Dict, Any, Optional, Tuple
import logging

# Assuming tool_adapter is in PYTHONPATH.
# If swisper/ is the root in PYTHONPATH:
from tool_adapter.mock_google import mock_google_shopping as search_fn 

logger = logging.getLogger(__name__)

class MockGoogleShoppingComponent(BaseComponent):
    outgoing_edges = 1 # Number of output connections

    def __init__(self):
        super().__init__()
        # Any specific initialization if needed

    def run(self, query: str) -> Tuple[Dict[str, Any], str]:
        logger.info(f"MockGoogleShoppingComponent received query: {query}")
        try:
            products = search_fn(q=query)
            # Handle cases where search_fn might return error dicts
            if isinstance(products, list) and products and isinstance(products[0], dict) and "error" in products[0]:
                logger.warning(f"Mock search for '{query}' returned an error: {products[0]['error']}")
                output = {"products": []} # Or pass error through
            else:
                output = {"products": products}
            return output, "output_1" # Standard Haystack component output format
        except Exception as e:
            logger.error(f"Exception in MockGoogleShoppingComponent for query '{query}': {e}", exc_info=True)
            # Return empty list or error structure
            return {"products": [], "error": str(e)}, "output_1"

    def run_batch(self, queries: List[str]) -> Tuple[Dict[str, Any], str]:
        # Optional: implement batch processing if needed
        results = []
        for query in queries:
            result, _ = self.run(query=query)
            results.append(result)
        # Consolidate results: {"products": [[products_for_q1], [products_for_q2], ...]}
        # Or, if component is meant to output a flat list of all products from all queries, adjust accordingly.
        # For now, let's assume batch output mirrors multiple single runs.
        return {"results_batch": results}, "output_1"


class SimplePythonRankingComponent(BaseComponent):
    outgoing_edges = 1

    def __init__(self):
        super().__init__()

    def _score(self, product: Dict[str, Any]) -> tuple:
        # Default to 0 for rating and infinity for price if not present or not a number
        try:
            rating = float(product.get("rating", 0.0))
        except (ValueError, TypeError):
            rating = 0.0
        try:
            price = float(product.get("price", float("inf")))
        except (ValueError, TypeError):
            price = float("inf")
        return (rating, -price) # Sort by rating (desc), then price (asc)

    def run(self, products: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], str]:
        logger.info(f"SimplePythonRankingComponent received {len(products)} products.")
        if not products or not isinstance(products, list):
            logger.warning("No products provided to rank or input is not a list.")
            return {"ranked_products": []}, "output_1"
        
        try:
            # Filter out any non-dictionary items just in case
            valid_products = [p for p in products if isinstance(p, dict)]
            ranked_list = sorted(valid_products, key=self._score, reverse=True)
            output = {"ranked_products": ranked_list}
            return output, "output_1"
        except Exception as e:
            logger.error(f"Exception in SimplePythonRankingComponent: {e}", exc_info=True)
            return {"ranked_products": [], "error": str(e)}, "output_1"
    
    def run_batch(self, products_batch: List[List[Dict[str, Any]]]) -> Tuple[Dict[str, Any], str]:
        results = []
        # The input here is expected to be a list of lists of products,
        # e.g., products_batch = [ [{"products": results_from_run1}], [{"products": results_from_run2}] ]
        # However, the component's run method expects a direct list of products.
        # This means the pipeline definition needs to ensure correct data flow (e.g. using `inputs` in `Pipeline.add_node`).
        # If `products_batch` is truly `List[List[Dict[str, Any]]]`, where each inner list is a list of products:
        for products_list in products_batch:
            result, _ = self.run(products=products_list) # Pass the inner list to run()
            results.append(result) # result is {"ranked_products": ...}
        return {"ranked_products_batch": results}, "output_1"


class ProductSelectorComponent(BaseComponent):
    outgoing_edges = 1

    def __init__(self):
        super().__init__()

    def run(self, ranked_products: List[Dict[str, Any]]) -> Tuple[Dict[str, Any], str]:
        logger.info(f"ProductSelectorComponent received {len(ranked_products)} ranked products.")
        if not ranked_products or not isinstance(ranked_products, list):
            logger.warning("No ranked products provided to select from or input is not a list.")
            output = {"selected_product": None}
        else:
            # Filter out non-dict items just in case
            valid_products = [p for p in ranked_products if isinstance(p, dict)]
            if not valid_products:
                logger.warning("Product list became empty after filtering non-dict items.")
                output = {"selected_product": None}
            else:
                top_product = valid_products[0]
                logger.info(f"Selected product: {top_product.get('name', 'Unknown name')}")
                output = {"selected_product": top_product}
        
        return output, "output_1"

    def run_batch(self, ranked_products_batch: List[List[Dict[str, Any]]]) -> Tuple[Dict[str, Any], str]:
        results = []
        # Similar to SimplePythonRankingComponent, this expects a list of lists of ranked products.
        for ranked_products_list in ranked_products_batch:
            result, _ = self.run(ranked_products=ranked_products_list)
            results.append(result) # result is {"selected_product": ...}
        return {"selected_products_batch": results}, "output_1"
