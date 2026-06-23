"""
Retriever.py -> embed the query, ask the store for nearest passages

Backend-agnostic. Whether config.vector_backend is chroma or pinecone, this code is identical - the stores handles the difference. Accepts injected store / embedder so it can be unit-tested without heavy depedencies.

"""

from __future__ import annotations

from config import settings
from src.retrieval.embedder import Embedder
from src.retrieval.stores import Passage, VectorStore, get_store


class Retriever:
    def __init__(self, store: VectorStore | None = None, embedder=None) -> None:
        self.store = store or get_store()
        self.embedder = embedder or Embedder()
    
    def search(self, query: str, k: int | None=None) -> list[Passage]:
        k = k or settings.top_k
        embedding = self.embedder.encode([query])[0]
        return self.store.query(self.embedder, k)