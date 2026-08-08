"""
stores.py — pluggable vector store behind one interface.

Backends take pre-computed embeddings (embedding happens in embedder.py), so
adding a third backend later means implementing two methods, nothing else.
Heavy client libraries are imported lazily inside each backend, so importing
this module never requires chromadb or pinecone to be installed.

Select the backend with config.vector_backend (env VECTOR_BACKEND):
    chroma   -> local, persisted to data/chroma/  (use for reproducible eval)
    pinecone -> hosted serverless                 (use for the live demo)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Protocol

from config import INDEX_DIR, settings


@dataclass
class Passage:
    text: str
    source: str
    question: str
    score: float      # Cosine similarit in ~[0, 1]
    url: str = ""     # exact NIH page -> citation can link to it


def _meta(question: str, source: str, url: str) -> dict:
    return{"question": question, "source": source, "url": url}


class VectorStore(Protocol):
    def upsert(self, ids, embeddings, documents, metadatas) -> None: ...
    def query(self, embedding, k) -> list[Passage]: ...
    def count(self) -> int: ...
    def reset(self) -> None: ...


class ChromaStore:
    def __init__(self) -> None:
        import chromadb
        INDEX_DIR.mkdir(parents=True, exist_ok=True)
        self.client = chromadb.PersistentClient(path=str(INDEX_DIR))
        self.coll = self.client.get_or_create_collection(
            settings.collection_name, metadata={"hnsw:space": "cosine"}
        )

    def upsert(self, ids, embeddings, documents, metadatas) -> None:
        self.coll.upsert(
            ids=ids, embeddings=embeddings, documents=documents, metadatas=metadatas
        )

    def query(self, embedding, k) -> list[Passage]:
        res = self.coll.query(
            query_embeddings=[embedding], n_results=k,
            include=["documents", "metadatas", "distances"],
        )
        out: list[Passage] = []
        for doc, meta, dist in zip(
            res["documents"][0], res["metadatas"][0], res["distances"][0]
        ):
            out.append(Passage(
                text=doc, source=meta.get("source", ""),
                question=meta.get("question", ""), url=meta.get("url", ""),
                score=1.0 - dist,
            ))
        return out

    def count(self) -> int:
        return self.coll.count()

    def reset(self) -> None:
        try:
            self.client.delete_collection(settings.collection_name)
        except Exception:
            pass
        self.coll = self.client.get_or_create_collection(
            settings.collection_name, metadata={"hnsw:space": "cosine"}
        )


class PineconeStore:
    def __init__(self) -> None:
        from pinecone import Pinecone, ServerlessSpec  # verify API for your pinecone version
        api_key = os.environ["PINECONE_API_KEY"]
        self.pc = Pinecone(api_key=api_key)
        name = settings.pinecone_index
        existing = [i["name"] for i in self.pc.list_indexes()]
        if name not in existing:
            self.pc.create_index(
                name=name, dimension=settings.embed_dim, metric="cosine",
                spec=ServerlessSpec(cloud=settings.pinecone_cloud,
                                    region=settings.pinecone_region),
            )
        self.index = self.pc.Index(name)

    def upsert(self, ids, embeddings, documents, metadatas) -> None:
        vectors = []
        for i, emb, doc, meta in zip(ids, embeddings, documents, metadatas):
            md = dict(meta)
            md["text"] = doc                 # Pinecone returns metadata, not docs
            vectors.append({"id": i, "values": emb, "metadata": md})
        for start in range(0, len(vectors), 100):   # upsert batch cap
            self.index.upsert(vectors=vectors[start:start + 100])

    def query(self, embedding, k) -> list[Passage]:
        res = self.index.query(vector=embedding, top_k=k, include_metadata=True)
        out: list[Passage] = []
        for m in res["matches"]:
            md = m.get("metadata", {})
            out.append(Passage(
                text=md.get("text", ""), source=md.get("source", ""),
                question=md.get("question", ""), url=md.get("url", ""),
                score=m["score"],
            ))
        return out

    def count(self) -> int:
        return self.index.describe_index_stats().get("total_vector_count", 0)

    def reset(self) -> None:
        try:
            self.index.delete(delete_all=True)
        except Exception:
            pass


def get_store() -> VectorStore:
    backend = settings.vector_backend
    if backend == "chroma":
        return ChromaStore()
    if backend == "pinecone":
        return PineconeStore()
    raise ValueError(f"unknown vector_backend: {backend!r} (use 'chroma' or 'pinecone')")
