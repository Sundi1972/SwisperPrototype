# swisper/haystack_pipeline/__init__.py
# This file makes Python treat the directory as a package.
from .rag import ask_doc, DOCUMENT_STORE, RAG_PIPELINE # Exposing for orchestrator and indexer
# from .indexer import main as run_indexer # If indexer is to be callable as a function
