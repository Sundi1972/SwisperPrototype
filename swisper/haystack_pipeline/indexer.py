import argparse
import logging
import os
import glob
from haystack.dataclasses import Document
from haystack.components.converters.text_file import TextFileToDocument 
# To add PDF support later:
# from haystack.components.converters.pypdf import PyPDFToDocument
# from haystack.components.preprocessors import DocumentSplitter

# Import the shared document store from rag.py
try:
    from .rag import DOCUMENT_STORE # Relative import if in the same package
except ImportError:
    # Fallback if running as a script from a different CWD or structure issues
    from haystack_pipeline.rag import DOCUMENT_STORE 

logger = logging.getLogger(__name__)

def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Index documents into Haystack Document Store.")
    parser.add_argument("paths", nargs="+", 
                        help="File paths or glob patterns for documents to index (e.g., 'docs/*.txt').")
    # Optional: Add arguments for specific document store settings or preprocessors if needed later.
    # parser.add_argument("--clean", action="store_true", help="Clear existing documents from the store before indexing.")

    args = parser.parse_args()

    if not DOCUMENT_STORE:
        logger.error("Document store from rag.py is not initialized. Exiting.")
        return

    # if args.clean:
    #     logger.info("Clearing existing documents from the store...")
    #     # Note: InMemoryDocumentStore doesn't have a simple 'delete_all_documents' like some others.
    #     # A workaround might be to re-initialize it, but that's tricky with shared instances.
    #     # For now, new documents will be added. If duplicates are an issue, handle content hashing or IDs.
    #     # This is a limitation of InMemoryDocumentStore if not re-instantiating.
    #     # Let's assume for now that we just add documents.
    #     logger.warning("Document store cleaning not implemented for InMemoryDocumentStore in this script. New documents will be added.")


    # For MVP, let's use TextFileToDocument.
    # PDF processing can be added later with PyPDFToDocument and DocumentSplitter.
    file_converter = TextFileToDocument()
    # pdf_converter = PyPDFToDocument() # For later
    # splitter = DocumentSplitter(split_by="word", split_length=200, split_overlap=20) # For later

    all_files_to_process = []
    for path_pattern in args.paths:
        expanded_paths = glob.glob(path_pattern, recursive=True)
        if not expanded_paths:
            logger.warning(f"No files found for pattern: {path_pattern}")
        all_files_to_process.extend(expanded_paths)
    
    if not all_files_to_process:
        logger.info("No files found to index with the given paths/patterns.")
        return

    logger.info(f"Found {len(all_files_to_process)} files to process for indexing: {all_files_to_process}")
    
    processed_documents = []
    for filepath in all_files_to_process:
        logger.info(f"Processing file: {filepath}")
        try:
            if filepath.lower().endswith(".txt"):
                # TextFileToDocument expects a list of sources
                conversion_output = file_converter.run(sources=[filepath]) 
                docs_from_file = conversion_output["documents"]
                logger.info(f"Converted {len(docs_from_file)} document(s) from {filepath}")
                processed_documents.extend(docs_from_file)
            # Add elif for .pdf here later
            else:
                logger.warning(f"Skipping unsupported file type: {filepath}. MVP handles .txt only.")
        except Exception as e:
            logger.error(f"Failed to process file {filepath}: {e}", exc_info=True)
    
    if processed_documents:
        logger.info(f"Writing {len(processed_documents)} processed documents to the Document Store...")
        # InMemoryEmbeddingRetriever in rag.py will handle embedding generation at query time.
        # So, just write documents with content.
        DOCUMENT_STORE.write_documents(processed_documents)
        logger.info(f"Successfully wrote documents. Total documents in store: {DOCUMENT_STORE.count_documents()}")
    else:
        logger.info("No documents were successfully processed to write to the store.")

if __name__ == "__main__":
    main()
