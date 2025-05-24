import json
import os
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)

# Determine path to mock_gpus.json relative to this file or an absolute path
# This assumes tool_adapter is one level down from swisper root, and tests is also one level down.
MOCK_DATA_PATH = os.path.join(os.path.dirname(__file__), '..', 'tests', 'data', 'mock_gpus.json')


def mock_google_shopping(q: str) -> List[Dict[str, Any]]:
    logger.info(f"Mock Google Shopping called with query: {q}")
    try:
        absolute_mock_data_path = os.path.abspath(MOCK_DATA_PATH)
        logger.debug(f"Attempting to load mock GPU data from: {absolute_mock_data_path}")

        if not os.path.exists(absolute_mock_data_path):
            logger.error(f"Mock data file not found at {absolute_mock_data_path}. Query: '{q}'")
            # Try an alternative common path if running from swisper root (e.g. if CWD is swisper/)
            alt_path = os.path.join("tests", "data", "mock_gpus.json") 
            if os.path.exists(alt_path):
                absolute_mock_data_path = alt_path
                logger.info(f"Found mock data at alternative relative path: {alt_path}")
            else:
                 logger.error(f"Alternative mock data file not found at {alt_path} either.")
                 return [{"error": "Mock data file not found.", "query": q}]

        with open(absolute_mock_data_path, 'r') as f:
            all_products = json.load(f)
        
        # Basic filtering: return products containing the query string (case-insensitive) in name or brand
        filtered_products = [
            p for p in all_products 
            if (q.lower() in p.get("name", "").lower()) or \
               (q.lower() in p.get("brand", "").lower())
        ]
        
        if not filtered_products and q: # If query doesn't match anything and query was not empty
            logger.warning(f"No direct match for query '{q}' in mock data. Returning first 2 items as fallback.")
            return all_products[:2] 
        elif not q: # If query is empty, return all products or a subset
             logger.warning("Empty query received. Returning all mock products.")
             return all_products


        logger.info(f"Returning {len(filtered_products)} mock products for query: {q}")
        return filtered_products

    except FileNotFoundError: # This might be redundant if os.path.exists is checked first
        logger.error(f"Mock data file not found at {MOCK_DATA_PATH} (resolved to {absolute_mock_data_path}). Query: '{q}'")
        return [{"error": "Mock data file not found.", "query": q}]
    except json.JSONDecodeError:
        logger.error(f"Error decoding JSON from {MOCK_DATA_PATH}. Query: '{q}'")
        return [{"error": "Error decoding mock data.", "query": q}]
    except Exception as e:
        logger.error(f"An unexpected error occurred in mock_google_shopping: {e}", exc_info=True)
        return [{"error": f"Unexpected error: {str(e)}", "query": q}]

# Renaming for clarity as per suggestion, though not strictly necessary if mapped directly
def mock_google_shopping_adapter(q: str) -> List[Dict[str, Any]]:
    return mock_google_shopping(q=q)

adapter_map = {
    "mock_google_shopping": mock_google_shopping_adapter # Mapping to the renamed/clarified adapter
    # "mock_google_shopping": mock_google_shopping # Could also map directly if no rename
}

def route(name: str, params: dict):
    if name in adapter_map:
        # Ensure all required parameters for the specific tool are passed.
        # For mock_google_shopping, 'q' is required.
        # This basic check can be expanded or made more generic if needed.
        if name == "mock_google_shopping" and 'q' not in params:
            logger.error(f"Query parameter 'q' missing for tool {name}")
            raise TypeError(f"Missing required parameter 'q' for tool {name}") # TypeError for missing args
        
        try:
            return adapter_map[name](**params)
        except TypeError as te: # Catching issues like unexpected keyword arguments if params don't match function signature
            logger.error(f"TypeError calling tool {name} with params {params}: {te}", exc_info=True)
            # Re-raise as a more specific error or handle as appropriate
            raise TypeError(f"Invalid parameters for tool {name}: {te}")

    else:
        logger.error(f"Unknown tool name in mock_adapter.route: {name}")
        raise ValueError(f"Unknown tool: {name}")
