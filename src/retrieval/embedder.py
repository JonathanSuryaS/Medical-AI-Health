# embedder.py -> where embeddings are produced

# index-build and query-time retrieval go through this, guarantees the corpus and queries live in the same vector space. Vectors are L2-normalized so cosine similarity behaves consistently across Chroma and Pinecone.

from __future__ import annotations
from config import settings



class Embedder:
    def __init__(self, model_name: str | None = None) -> None:
        from sentence_transformer import SentenceTransformer
        self.model = SentenceTransformer(model_name or settings.embed_model)
    
    def encode(self, texts: list[str]) -> list[list[float]]:
        vecs = self.model.encode(
            texts, normalize_embeddings=True, convert_to_numpy=True
        )
        return vecs.tolist()

