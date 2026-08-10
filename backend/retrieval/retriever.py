"""
retriever.py -> embed the query, ask the store for the nearest passages.

Backend-agnostic: whether config.vector_backend is chroma or pinecone, this code
is identical — stores.py absorbs the difference. Accepts an injected store and
embedder so it can be unit-tested without downloading models or hitting Pinecone.
"""

from __future__ import annotations

from config import settings
from backend.retrieval.embedder import Embedder
from backend.retrieval.stores import Passage, VectorStore, get_store


class Retriever:
    def __init__(self, store: VectorStore | None = None, embedder=None) -> None:
        self.store = store or get_store()
        self.embedder = embedder or Embedder()

    def search(self, query: str, k: int | None = None) -> list[Passage]:
        k = k or settings.top_k
        embedding = self.embedder.encode([query])[0]
        # BUGFIX: was `self.store.query(self.embedder, k)` — passed the Embedder
        # object instead of the vector it had just computed.
        return self.store.query(embedding, k)

    def search_or_abstain(self, query: str, k: int | None = None) -> list[Passage]:
        """Retrieval with the abstention gate applied.

        Returns [] when the best passage scores below settings.min_retrieval_score.
        An empty list is the signal the generation layer uses to refuse and refer
        the user to a clinician, rather than hallucinating from weak context.
        """
        passages = self.search(query, k)
        if not passages or passages[0].score < settings.min_retrieval_score:
            return []
        return passages