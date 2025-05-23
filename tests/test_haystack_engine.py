import unittest
from haystack.pipelines import Pipeline
from haystack import Document
from engine.haystack_engine import get_haystack_pipeline

class TestHaystackEngine(unittest.TestCase):

    def test_get_haystack_pipeline(self):
        """
        Tests if get_haystack_pipeline returns a valid Haystack Pipeline object
        and has the expected nodes.
        """
        pipeline = get_haystack_pipeline()
        self.assertIsInstance(pipeline, Pipeline, "Returned object is not a Haystack Pipeline.")
        
        # Check for the presence of retriever and ranker nodes by their default names
        # (or specific names if they are set in haystack_engine.py)
        node_names = [node_id for node_id in pipeline.graph.nodes]
        self.assertIn("BM25Retriever", node_names, "BM25Retriever node is missing.")
        self.assertIn("SentenceTransformersRanker", node_names, "SentenceTransformersRanker node is missing.")
        self.assertTrue(len(node_names) >= 2, "Pipeline should have at least two nodes.")

    def test_haystack_pipeline_execution(self):
        """
        Tests the full execution of the Haystack pipeline with sample documents and a query.
        """
        pipeline = get_haystack_pipeline()
        document_store = pipeline.get_document_store()
        document_store.delete_documents() # Ensure clean state

        sample_docs = [
            Document(content="cheap camera", meta={"name": "CheapCam", "price": 50, "rating": 3.5}),
            Document(content="average camera", meta={"name": "AvgCam", "price": 150, "rating": 4.0}),
            Document(content="expensive camera", meta={"name": "ProCam", "price": 500, "rating": 4.8}),
            Document(content="another cheap camera", meta={"name": "BudgetCam", "price": 60, "rating": 3.8}),
        ]
        document_store.write_documents(sample_docs)
        self.assertEqual(document_store.get_document_count(), len(sample_docs))

        # Parameters for retriever and ranker
        # BM25Retriever is the name of the retriever node in haystack_engine.py
        # SentenceTransformersRanker is the name of the ranker node in haystack_engine.py
        retriever_top_k = 3
        ranker_top_k = 2

        result = pipeline.run(
            query="cheap camera",
            params={
                "BM25Retriever": {"top_k": retriever_top_k},
                "SentenceTransformersRanker": {"top_k": ranker_top_k}
            }
        )

        self.assertIn("documents", result, "Pipeline result should contain 'documents' key.")
        self.assertIsInstance(result["documents"], list, "'documents' should be a list.")
        for doc in result["documents"]:
            self.assertIsInstance(doc, Document, "Each item in 'documents' should be a Haystack Document.")
        
        self.assertTrue(len(result["documents"]) <= ranker_top_k, 
                        f"Number of returned documents ({len(result['documents'])}) exceeds Ranker's top_k ({ranker_top_k}).")
        
        # Optionally, check if the content of returned docs makes sense for the query
        if result["documents"]:
            first_doc_meta = result["documents"][0].meta
            self.assertIn("price", first_doc_meta) # Basic check for expected meta fields
            self.assertIn("rating", first_doc_meta)

if __name__ == '__main__':
    unittest.main()
