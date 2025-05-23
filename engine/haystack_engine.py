from haystack.document_stores import InMemoryDocumentStore
from haystack.nodes import BM25Retriever, SentenceTransformersRanker
from haystack.pipelines import Pipeline

def get_haystack_pipeline():
    """
    Initializes and returns a Haystack pipeline with a BM25Retriever and a SentenceTransformersRanker.
    """
    # Initialize the document store
    document_store = InMemoryDocumentStore(use_bm25=True)

    # Initialize the retriever
    retriever = BM25Retriever(document_store=document_store)

    # Initialize the ranker
    ranker = SentenceTransformersRanker(model_name_or_path='cross-encoder/ms-marco-MiniLM-L-6-v2')

    # Create the pipeline
    pipeline = Pipeline()

    # Add nodes to the pipeline
    pipeline.add_node(component=retriever, name="BM25Retriever", inputs=["Query"])
    pipeline.add_node(component=ranker, name="SentenceTransformersRanker", inputs=["BM25Retriever"])

    return pipeline

if __name__ == '__main__':
    # Example usage (optional, for testing)
    example_pipeline = get_haystack_pipeline()
    print("Haystack pipeline initialized successfully.")
    # You would typically add documents to the document_store and then run queries
    # For example:
    # from haystack import Document
    # document_store.write_documents([Document(content="This is a test document.")])
    # result = example_pipeline.run(query="What is this document about?")
    # print(result)
