from haystack.pipelines import Pipeline
import logging

try:
    from .haystack_components import (
        MockGoogleShoppingComponent,
        SimplePythonRankingComponent,
        ProductSelectorComponent
    )
except ImportError: 
    from contract_engine.haystack_components import ( # Fallback for some execution contexts
        MockGoogleShoppingComponent,
        SimplePythonRankingComponent,
        ProductSelectorComponent
    )

logger = logging.getLogger(__name__)

def create_product_selection_pipeline() -> Pipeline:
    pipeline = Pipeline()

    search_node = MockGoogleShoppingComponent()
    rank_node = SimplePythonRankingComponent()
    select_node = ProductSelectorComponent()

    # Pipeline definition:
    # 1. ProductSearch node takes "Query" as input. Its run method expects 'query'.
    pipeline.add_node(component=search_node, name="ProductSearch", inputs=["Query"])
    
    # 2. ProductRanker node takes the output of ProductSearch.
    # ProductSearch outputs a dict like {"products": [...]}.
    # ProductRanker's run method expects a 'products' parameter.
    pipeline.add_node(component=rank_node, name="ProductRanker", inputs=["ProductSearch"]) 
    
    # 3. ProductSelector node takes the output of ProductRanker.
    # ProductRanker outputs a dict like {"ranked_products": [...]}.
    # ProductSelector's run method expects a 'ranked_products' parameter.
    pipeline.add_node(component=select_node, name="ProductSelector", inputs=["ProductRanker"])

    logger.info("Product Selection Pipeline created successfully.")
    return pipeline

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    
    # This example assumes mock_gpus.json is in tests/data/ relative to where this script might be run from
    # or that tool_adapter.mock_google.py correctly resolves its path.
    # For this test to run, PYTHONPATH might need to be set to include the 'swisper' root directory.
    # Example: export PYTHONPATH="${PYTHONPATH}:/path/to/your/swisper_mvp_project" (if swisper is root)
    # or if swisper_mvp_project contains swisper/: export PYTHONPATH="${PYTHONPATH}:/path/to/your/swisper_mvp_project"
    
    logger.info("Attempting to create and run product selection pipeline for local testing...")
    
    try:
        product_pipeline = create_product_selection_pipeline()
        test_query = "Mock GPU" 
        logger.info(f"Running pipeline with query: '{test_query}'")
        
        # The `run` method of Pipeline expects parameters for the first node by their input names.
        # The first node "ProductSearch" expects "Query".
        pipeline_result = product_pipeline.run(query=test_query) 
        
        logger.info("Pipeline execution finished.")
        
        # The output of `pipeline.run()` is a dictionary where keys are node names.
        # The values are the direct output of each node's `run` method (the tuple `(dict, output_edge_name)`).
        selected_product_node_output = pipeline_result.get("ProductSelector") # This is ({"selected_product": ...}, "output_1")
        
        if selected_product_node_output and isinstance(selected_product_node_output, tuple):
            selected_product_data = selected_product_node_output[0] # Get the dictionary part
            selected_product = selected_product_data.get("selected_product")
            if selected_product:
                logger.info(f"Selected Product: {selected_product.get('name', 'N/A')} - Price: {selected_product.get('price', 'N/A')}")
            else:
                logger.info("No product was selected by the pipeline (ProductSelector output key 'selected_product' is None or missing).")
        else:
            logger.warning(f"ProductSelector output was not in the expected format: {selected_product_node_output}")

        # For debugging, print the full result from each node
        # for node_name, output_tuple in pipeline_result.items():
        #    logger.debug(f"Output from {node_name}: {output_tuple[0] if isinstance(output_tuple, tuple) else output_tuple}")

    except Exception as e:
        logger.error(f"Error running product selection pipeline test: {e}", exc_info=True)
        logger.error("Ensure that MOCK_DATA_PATH in tool_adapter/mock_google.py is correctly pointing to your tests/data/mock_gpus.json file.")
        logger.error("Also ensure PYTHONPATH is set up to find 'tool_adapter' and other project modules if running this script directly.")
