"""
smoke_test.py -> prove the retrieval spine works before building anything on top.

    python -m src.retrieval.smoke_test

Checks, in order:
  1. the store has vectors at all (catches "build_index never ran")
  2. an in-domain query returns passages with plausible scores + provenance
  3. an out-of-domain query gets abstained on (catches an inverted score sign,
     which is the single easiest way to silently break the whole system)
"""

from __future__ import annotations

from config import settings
from src.retrieval.retriever import Retriever
from src.retrieval.stores import get_store

IN_DOMAIN = [
    "What are the symptoms of alpha-1 antitrypsin deficiency?",
    "How is type 2 diabetes treated?",
    "What causes Parkinson's disease?",
]

OUT_OF_DOMAIN = [
    "Who won the 2022 FIFA World Cup?",
    "Write me a Python function to reverse a linked list.",
]


def main() -> None:
    store = get_store()
    n = store.count()
    print(f"backend={settings.vector_backend}  vectors={n:,}\n")
    if n == 0:
        raise SystemExit("store is empty — run `python -m src.ingest.build_index` first.")

    r = Retriever(store=store)

    print("=" * 70)
    print("IN-DOMAIN (expect high scores + real NIH sources)")
    print("=" * 70)
    for q in IN_DOMAIN:
        hits = r.search(q)
        print(f"\nQ: {q}")
        if not hits:
            print("   !! no hits — something is wrong")
            continue
        for h in hits[:2]:
            print(f"   [{h.score:.3f}] {h.source:<20} {h.text[:90]}...")
            print(f"           url: {h.url or '(none)'}")

    print("\n" + "=" * 70)
    print(f"OUT-OF-DOMAIN (expect abstention at score < {settings.min_retrieval_score})")
    print("=" * 70)
    for q in OUT_OF_DOMAIN:
        hits = r.search(q)
        top = hits[0].score if hits else 0.0
        gated = r.search_or_abstain(q)
        verdict = "ABSTAIN ✅" if not gated else "ANSWERED ⚠️  (threshold too low?)"
        print(f"\nQ: {q}\n   top score {top:.3f} -> {verdict}")

    print("\n" + "-" * 70)
    print("Sanity check: in-domain scores should be clearly ABOVE out-of-domain")
    print("scores. If they're inverted, Chroma is returning L2 distance rather")
    print("than cosine and the 1.0 - dist conversion in stores.py is wrong.")


if __name__ == "__main__":
    main()