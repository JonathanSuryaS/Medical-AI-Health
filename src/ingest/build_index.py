# build_index.py -> embed the corpus and load it into the configured vector store
# Honors config.vector_backend: builds into local Chroma OR hosted Pinecone with the same code. Run once per corpus change

from __future__ import annotations

from config import RAW_CORPUS, settings
from src.ingest.load_medquad import load_corpus
from src.retrieval.embedder import Embedder
from src.retrieval.stores import get_store


