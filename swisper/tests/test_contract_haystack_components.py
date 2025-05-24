import pytest
from unittest.mock import patch, MagicMock

# Assuming components are in swisper.contract_engine (via __init__.py)
# This requires PYTHONPATH to be set up correctly if tests are run from root
# or if the test runner discovers tests within the swisper package.
# For local testing, if swisper/ is the CWD, then:
# from contract_engine.haystack_components import ... might work if PYTHONPATH includes '.'
# However, for consistency with how modules are usually structured & imported:
from swisper.contract_engine.haystack_components import (
    MockGoogleShoppingComponent,
    SimplePythonRankingComponent,
    ProductSelectorComponent
)
# Fallback for simpler local execution if PYTHONPATH is not set to include parent of swisper
# try:
#     from swisper.contract_engine.haystack_components import (
#         MockGoogleShoppingComponent,
#         SimplePythonRankingComponent,
#         ProductSelectorComponent
#     )
# except ImportError:
#     # This assumes tests are run from a directory where 'swisper' is a subdirectory,
#     # and 'swisper' itself is not directly in PYTHONPATH, but its parent is.
#     # Or, that the test runner adds 'swisper' to sys.path.
#     # This is common if tests are in 'tests/' and code in 'swisper/'.
#     # A more robust way is to ensure your test execution environment correctly sets PYTHONPATH
#     # to include the project root (the directory containing 'swisper').
#     from ..contract_engine.haystack_components import ( # If tests/ is alongside contract_engine/
#         MockGoogleShoppingComponent,
#         SimplePythonRankingComponent,
#         ProductSelectorComponent
#     )


@pytest.fixture
def mock_search_results():
    return [
        {"name": "GPU A", "price": 300, "rating": 4.5},
        {"name": "GPU B", "price": 250, "rating": 4.0},
        {"name": "GPU C", "price": 350, "rating": 4.8},
    ]

class TestMockGoogleShoppingComponent:
    # The path to patch should be where 'search_fn' is looked up by the component.
    # If haystack_components.py has 'from tool_adapter.mock_google import mock_google_shopping as search_fn',
    # then 'search_fn' is now part of the 'haystack_components' module's namespace.
    @patch('swisper.contract_engine.haystack_components.search_fn') 
    def test_run_success(self, mock_search, mock_search_results):
        mock_search.return_value = mock_search_results
        component = MockGoogleShoppingComponent()
        query = "test gpu"
        output, edge = component.run(query=query)
        
        mock_search.assert_called_once_with(q=query)
        assert edge == "output_1"
        assert output["products"] == mock_search_results

    @patch('swisper.contract_engine.haystack_components.search_fn')
    def test_run_search_error_response(self, mock_search):
        # Test when the search_fn itself returns a list containing an error dict
        mock_search.return_value = [{"error": "API limit reached"}]
        component = MockGoogleShoppingComponent()
        output, _ = component.run(query="test")
        # Based on component's logic: if isinstance(products, list) and products and isinstance(products[0], dict) and "error" in products[0]:
        # it will log a warning and set output = {"products": []}
        assert output["products"] == [] 

    @patch('swisper.contract_engine.haystack_components.search_fn')
    def test_run_search_exception(self, mock_search):
        mock_search.side_effect = Exception("Network error")
        component = MockGoogleShoppingComponent()
        output, _ = component.run(query="test")
        assert output["products"] == [] # Default fallback on exception
        assert "error" in output # Component should add an error key
        assert output["error"] == "Network error"


class TestSimplePythonRankingComponent:
    def test_run_ranking(self, mock_search_results):
        component = SimplePythonRankingComponent()
        # Results are: A (300, 4.5), B (250, 4.0), C (350, 4.8)
        # Score logic: (rating, -price). Sorted reverse=True.
        # C: (4.8, -350) -> sort key
        # A: (4.5, -300) -> sort key
        # B: (4.0, -250) -> sort key
        # Expected order by (rating DESC, price ASC): C, A, B
        expected_ranked_names = ["GPU C", "GPU A", "GPU B"]
        
        output, edge = component.run(products=mock_search_results)
        assert edge == "output_1"
        ranked_products = output["ranked_products"]
        assert len(ranked_products) == 3
        assert [p["name"] for p in ranked_products] == expected_ranked_names

    def test_run_empty_list(self):
        component = SimplePythonRankingComponent()
        output, _ = component.run(products=[])
        assert output["ranked_products"] == []

    def test_run_with_non_dict_items(self):
        component = SimplePythonRankingComponent()
        mixed_input = [
            {"name": "GPU A", "price": 300, "rating": 4.5},
            None, # Non-dict item
            {"name": "GPU C", "price": 350, "rating": 4.8},
            "not a dict"
        ]
        expected_ranked_names = ["GPU C", "GPU A"] # Only valid dicts should be ranked
        output, _ = component.run(products=mixed_input)
        ranked_products = output["ranked_products"]
        assert len(ranked_products) == 2
        assert [p["name"] for p in ranked_products] == expected_ranked_names
        
    def test_run_with_missing_fields(self):
        component = SimplePythonRankingComponent()
        products_missing_fields = [
            {"name": "GPU A", "price": 300}, # Missing rating
            {"name": "GPU B", "rating": 4.0}, # Missing price
            {"name": "GPU C"}, # Missing price and rating
            {"name": "GPU D", "price": "expensive", "rating": "high"} # Invalid types
        ]
        # Expected: D (0, inf), C (0, inf), B (4.0, inf), A (0, 300)
        # Sorted by (rating DESC, price ASC):
        # B (4.0, inf)
        # A (0, 300)
        # C (0, inf) - order relative to D depends on stability of sort for price=inf
        # D (0, inf)
        # The component's _score defaults to 0.0 for rating, float('inf') for price.
        # Score for A: (0.0, -300)
        # Score for B: (4.0, -inf)
        # Score for C: (0.0, -inf)
        # Score for D: (0.0, -inf) (rating="high" becomes 0.0, price="expensive" becomes inf)
        # Sorted reverse by this score: B, A, then C and D (order between C,D might vary if not stable)
        # Let's check if B is first and A is second.
        
        output, _ = component.run(products=products_missing_fields)
        ranked_products = output["ranked_products"]
        assert len(ranked_products) == 4
        assert ranked_products[0]["name"] == "GPU B"
        assert ranked_products[1]["name"] == "GPU A"
        # The order of C and D might be ambiguous if sort isn't stable for equal primary keys (rating)
        # and equal secondary keys (price=inf). Let's just check they are present.
        assert {"name": "GPU C"} in ranked_products 
        assert {"name": "GPU D", "price": "expensive", "rating": "high"} in ranked_products


class TestProductSelectorComponent:
    def test_run_selection(self, mock_search_results): 
        component = ProductSelectorComponent()
        # Assume mock_search_results are already ranked for simplicity of this test's focus
        # Let's use a pre-defined ranked list as input
        ranked_list = [
            {"name": "GPU C", "price": 350, "rating": 4.8}, # Top product
            {"name": "GPU A", "price": 300, "rating": 4.5},
            {"name": "GPU B", "price": 250, "rating": 4.0},
        ]
        output, edge = component.run(ranked_products=ranked_list)
        assert edge == "output_1"
        assert output["selected_product"] == ranked_list[0] 
        assert output["selected_product"]["name"] == "GPU C"

    def test_run_empty_list(self):
        component = ProductSelectorComponent()
        output, _ = component.run(ranked_products=[])
        assert output["selected_product"] is None

    def test_run_with_non_dict_items(self):
        component = ProductSelectorComponent()
        mixed_input = [
            None, # Non-dict item
            {"name": "GPU A", "price": 300, "rating": 4.5}, # This should be selected
            "not a dict"
        ]
        output, _ = component.run(ranked_products=mixed_input)
        assert output["selected_product"] is not None
        assert output["selected_product"]["name"] == "GPU A"

    def test_run_with_only_non_dict_items(self):
        component = ProductSelectorComponent()
        invalid_input = [None, "string1", 123]
        output, _ = component.run(ranked_products=invalid_input)
        assert output["selected_product"] is None
