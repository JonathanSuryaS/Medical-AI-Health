# build_index.py -> embed the corpus and load it into the configured vector store
#
# Honors config.vector_backend: builds into local Chroma OR hosted Pinecone with
# the same code path. Run once per corpus change.
#
#   VECTOR_BACKEND=chroma   python -m src.ingest.build_index      # eval / reproducible
#   VECTOR_BACKEND=pinecone python -m src.ingest.build_index      # live demo
#
# --reset wipes the collection first (use when chunking or embed model changes,
# otherwise stale vectors from a previous run linger and quietly skew recall).

from __future__ import annotations

import argparse
import time

from config import RAW_CORPUS, settings
from src.ingest.load_medquad import load_corpus
from src.retrieval.embedder import Embedder
from src.retrieval.stores import get_store

BATCH = 256  # embed + upsert in batches: keeps RAM flat and gives progress output


def build(reset: bool = False) -> None:
    print(f"[build_index] backend = {settings.vector_backend}")
    print(f"[build_index] embed model = {settings.embed_model} ({settings.embed_dim}-dim)")

    docs = load_corpus(RAW_CORPUS)
    if not docs:
        raise SystemExit("[build_index] corpus is empty — run medquad_xml_to_csv first.")

    embedder = Embedder()
    store = get_store()

    if reset:
        print("[build_index] resetting collection...")
        store.reset()

    t0 = time.time()
    total = len(docs)
    for start in range(0, total, BATCH):
        batch = docs[start:start + BATCH]

        ids = [d.id for d in batch]
        documents = [d.text for d in batch]
        metadatas = [
            {"question": d.question, "source": d.source, "url": d.url}
            for d in batch
        ]
        embeddings = embedder.encode(documents)

        store.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas,
        )

        done = min(start + BATCH, total)
        elapsed = time.time() - t0
        rate = done / elapsed if elapsed else 0
        eta = (total - done) / rate if rate else 0
        print(f"  {done:>6}/{total}  ({done/total:5.1%})  "
              f"{rate:6.0f} chunks/s  eta {eta/60:4.1f}m", flush=True)

    print(f"\n[build_index] done in {(time.time()-t0)/60:.1f} min")
    print(f"[build_index] store reports {store.count()} vectors.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true",
                    help="wipe the collection before building")
    args = ap.parse_args()
    build(reset=args.reset)