import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

from engine.contract_engine import ContractStateMachine
from haystack import Document
from engine.haystack_engine import get_haystack_pipeline # For type hinting or direct use if needed

# Dummy template and schema paths for testing
TEST_TEMPLATE_PATH = "contract_templates/purchase_item.yaml"
TEST_SCHEMA_PATH = "schemas/purchase_item.schema.json"

# Ensure dummy files exist for ContractStateMachine instantiation if not mocking load_template
# For simplicity, we assume these files exist or their loading is mocked.
# If they must exist, you'd create them here or in a setUpClass.
# Path(TEST_TEMPLATE_PATH).parent.mkdir(parents=True, exist_ok=True)
# Path(TEST_SCHEMA_PATH).parent.mkdir(parents=True, exist_ok=True)
# with open(TEST_TEMPLATE_PATH, "w") as f:
#     f.write("template_content: dummy") # Minimal content
# with open(TEST_SCHEMA_PATH, "w") as f:
#     f.write("{}") # Minimal valid JSON schema


class TestContractStateMachineHaystack(unittest.TestCase):

    @patch("engine.contract_engine.search_product")
    @patch("engine.contract_engine.ContractStateMachine.load_template") # Mock template loading
    def setUp(self, mock_load_template, mock_search_product):
        """
        Set up the test environment before each test.
        Mocks external API calls and template loading.
        """
        # Configure mock_load_template to return a basic contract structure
        mock_load_template.return_value = {
            "name": "Test Contract",
            "version": "1.0",
            "parameters": {},
            "states": {}, # Add states if your FSM logic depends on them during init
        }
        
        self.engine = ContractStateMachine(
            template_path=TEST_TEMPLATE_PATH, 
            schema_path=TEST_SCHEMA_PATH
        )
        # Ensure a fresh pipeline and document store for each test
        self.engine.haystack_pipeline = get_haystack_pipeline() 
        self.engine.haystack_pipeline.get_document_store().delete_documents()

        # It's also good practice to mock other external calls if they might be triggered
        # and are not the focus of the current test.
        self.mock_analyze_diff = patch("engine.contract_engine.analyze_product_differences").start()
        self.mock_analyze_pref = patch("engine.contract_engine.analyze_user_preferences").start()
        self.mock_filter_llm = patch("engine.contract_engine.filter_products_with_llm").start()
        self.mock_check_compat = patch("engine.contract_engine.check_product_compatibility").start()
        
        # Configure default return values for helper mocks if needed
        self.mock_analyze_diff.return_value = "Feature A vs Feature B"
        self.mock_analyze_pref.return_value = ["Feature A"]
        # filter_products_with_llm is expected to return a list of product dicts
        self.mock_filter_llm.return_value = [] 
        self.mock_check_compat.return_value = {"compatible": True}


    def tearDown(self):
        # Stop all patches started in setUp
        patch.stopall()

    @patch("engine.contract_engine.search_product")
    def test_search_state_uses_haystack(self, mock_search_product):
        """
        Tests that the search state correctly uses Haystack:
        - Populates the document store.
        - Stores Haystack Document objects in self.search_results.
        """
        sample_api_products = [
            {"name": "TestCam 1", "description": "A decent camera", "price": 100, "rating": 4.0, "product_id": "p1"},
            {"name": "TestCam 2", "description": "A budget camera", "price": 50, "rating": 3.5, "product_id": "p2"},
        ]
        mock_search_product.return_value = sample_api_products

        self.engine.fill_parameters({"product": "test camera"})
        
        # Transition: start -> search
        self.engine.next() # From start to search
        search_state_output = self.engine.next() # Executes search state

        doc_store = self.engine.haystack_pipeline.get_document_store()
        self.assertEqual(doc_store.get_document_count(), len(sample_api_products),
                         "Document store count should match number of products from API.")

        self.assertIsInstance(self.engine.search_results, list, "search_results should be a list.")
        self.assertTrue(all(isinstance(doc, Document) for doc in self.engine.search_results),
                        "All items in search_results should be Haystack Document objects.")

        # Check that the content/meta of these documents correspond to the mock product data.
        # The number of documents in search_results can be less than API results due to Haystack ranking (top_k)
        # So, we check if the documents found are a subset of the original API products.
        
        # Based on the current haystack_engine and contract_engine, 
        # BM25Retriever top_k=10, SentenceTransformerRanker top_k=5.
        # So, with 2 products, both should be in search_results.
        self.assertEqual(len(self.engine.search_results), len(sample_api_products),
                         "Number of documents in search_results should match API results for small N")

        for doc in self.engine.search_results:
            self.assertIn(doc.meta["product_id"], [p["product_id"] for p in sample_api_products])
            original_product = next(p for p in sample_api_products if p["product_id"] == doc.meta["product_id"])
            
            expected_content_parts = [
                str(original_product.get("name", "")),
                str(original_product.get("description", ""))
            ]
            # Add other fields if they are part of `content_str` in contract_engine's search state
            # if "snippet" in original_product: 
            #    expected_content_parts.append(str(original_product["snippet"]))
            expected_content = " | ".join(filter(None, expected_content_parts))
            
            self.assertEqual(doc.content, expected_content)
            self.assertEqual(doc.meta["name"], original_product["name"])
            self.assertEqual(doc.meta["price"], original_product["price"])
            self.assertEqual(doc.meta["rating"], original_product["rating"])

    def test_rank_and_select_with_haystack_documents(self):
        """
        Tests the rank_and_select method with a list of Haystack Document objects.
        """
        sample_documents = [
            Document(content="Product A", meta={"name": "A", "price": 100, "rating": 4.0, "product_id": "A1"}),
            Document(content="Product B", meta={"name": "B", "price": 200, "rating": 4.5, "product_id": "B1"}), # Higher rating, higher price
            Document(content="Product C", meta={"name": "C", "price": 150, "rating": 4.5, "product_id": "C1"}), # Higher rating, lower price
            Document(content="Product D", meta={"name": "D", "price": 100, "rating": 3.0, "product_id": "D1"}),
            Document(content="Product E", meta={"name": "E", "price": None, "rating": 4.8, "product_id": "E1"}), # Highest rating, price None
            Document(content="Product F", meta={"name": "F", "price": 50, "rating": None, "product_id": "F1"}), # Price 50, rating None (should be 0)
        ]

        # Expected ranking: E (4.8, inf price) -> C (4.5, 150) -> B (4.5, 200) -> A (4.0, 100) -> F (0, 50) -> D (3.0, 100)
        # The rank_and_select method returns the *meta* of the best document.
        
        # Case 1: Product E should be best (highest rating, price is None which becomes float('inf'))
        # rank_and_select sorts by (rating, -price), higher is better.
        # E: (4.8, -inf) -> highest
        # C: (4.5, -150)
        # B: (4.5, -200)
        # A: (4.0, -100)
        # F: (0, -50)
        # D: (3.0, -100)
        
        best_product_meta = self.engine.rank_and_select(sample_documents)
        self.assertEqual(best_product_meta["product_id"], "E1", "Product E should be ranked highest.")

        # Test with a subset where price matters more for same high rating
        subset_docs = [sample_documents[1], sample_documents[2]] # B and C
        best_of_subset = self.engine.rank_and_select(subset_docs)
        self.assertEqual(best_of_subset["product_id"], "C1", "Product C should be chosen over B due to lower price.")
        
        # Test with no documents
        empty_selection = self.engine.rank_and_select([])
        self.assertEqual(empty_selection["reason"], "No matching products found after filtering.")
        self.assertIsNone(empty_selection["price"])

    @patch("engine.contract_engine.search_product")
    @patch("engine.contract_engine.filter_products_with_llm")
    @patch("engine.contract_engine.analyze_product_differences")
    def test_full_flow_to_filter_state_with_haystack(self, mock_analyze_diff, mock_filter_llm, mock_search_product):
        """
        A more comprehensive test for a common path through the state machine,
        focusing on Haystack integration points up to the filter state.
        """
        # --- Setup for search state ---
        api_products = [
            {"name": "CamX", "description": "Good camera", "price": 120, "rating": 4.2, "product_id": "CX"},
            {"name": "CamY", "description": "Okay camera", "price": 80, "rating": 3.8, "product_id": "CY"},
            {"name": "CamZ", "description": "Pro camera", "price": 250, "rating": 4.7, "product_id": "CZ"},
        ]
        mock_search_product.return_value = api_products
        self.engine.fill_parameters({"product": "camera"})
        
        # start -> search
        self.engine.next()
        search_output = self.engine.next() # Execute search state

        self.assertEqual(self.engine.state, "filter", 
                         f"Expected to be in filter state if <=4 results, but in {self.engine.state}. Output: {search_output}")
        self.assertTrue(len(self.engine.search_results) <= 5 and len(self.engine.search_results) > 0) # Haystack ranker top_k is 5
        
        # --- Setup for filter state ---
        # filter_products_with_llm expects a list of product dicts (metas) and returns a filtered list of dicts
        # Let's say LLM filters down to CamX and CamZ
        llm_filtered_metas = [
            {"name": "CamX", "description": "Good camera", "price": 120, "rating": 4.2, "product_id": "CX", "llm_reason": "Good fit"},
            {"name": "CamZ", "description": "Pro camera", "price": 250, "rating": 4.7, "product_id": "CZ", "llm_reason": "Best quality"},
        ]
        mock_filter_llm.return_value = llm_filtered_metas
        
        # search -> filter
        # (No user input needed here as we skipped clarify_preferences by having few results)
        filter_output = self.engine.next() # Execute filter state
        
        self.assertEqual(self.engine.state, "check_compatibility")
        self.assertIsNotNone(self.engine.filtered_results, "filtered_results should be set.")
        self.assertEqual(len(self.engine.filtered_results), len(llm_filtered_metas),
                         "Number of filtered_results (Haystack Docs) should match LLM output metas.")

        for doc in self.engine.filtered_results:
            self.assertIsInstance(doc, Document)
            self.assertIn(doc.meta["product_id"], [m["product_id"] for m in llm_filtered_metas])
            # Check if LLM's modifications (e.g. "llm_reason") are in the doc.meta
            if doc.meta["product_id"] == "CX":
                self.assertEqual(doc.meta.get("llm_reason"), "Good fit")


if __name__ == '__main__':
    unittest.main()
