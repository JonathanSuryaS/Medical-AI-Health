"""
pipeline.py — the spine. One object, one method, one call path.
 
    from src.pipeline import Pipeline
    ans = Pipeline().ask("What are the symptoms of AAT deficiency?")
 
Everything above this (FastAPI, the eval harness, the CLI) calls ask() and
nothing else. Everything below it (retriever, generator, stores, providers) is
an implementation detail this class hides. When guardrails and PII land, they
wrap this method -- they do not get sprinkled through the layers underneath.
 
Keeping the composition in one place is what makes the eval reproducible: the
harness exercises the exact object the API serves, not a re-assembled lookalike.
"""

from __future__ import annotations
 
from config import settings
from src.generation.generator import Answer, Generator
from src.retrieval.retriever import Retriever
                


class Pipeline:
    def __init__(self, retriever: Retriever | None = None,
                 generator: Generator | None = None) -> None:
        self.retriever = retriever or Retriever()
        self.generator = generator or Generator()
 
    def ask(self, question: str, k: int | None = None) -> Answer:
        # search_or_abstain() returns [] when the top passage scores below
        # settings.min_retrieval_score. Generator.answer() treats [] as "refuse".
        # The gate is therefore enforced in two places and bypassable in neither.
        passages = self.retriever.search_or_abstain(question, k=k)
        return self.generator.answer(question, passages)


if __name__ == "__main__":
    import sys
 
    q = " ".join(sys.argv[1:]) or "What are the symptoms of alpha-1 antitrypsin deficiency?"
    ans = Pipeline().ask(q)
 
    print(f"\nQ: {q}")
    print(f"provider={ans.provider}  backend={settings.vector_backend}  "
          f"abstained={ans.abstained}\n")
    print(ans.text)
    if ans.citations:
        print("\nSources:")
        for c in ans.citations:
            print(f"  [{c.n}] {c.source} — {c.url or '(no url)'}")