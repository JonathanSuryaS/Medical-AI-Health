"""
pipeline.py -- the spine. One object, one method, one call path.

    from src.pipeline import Pipeline
    ans = Pipeline().ask("What are the symptoms of AAT deficiency?")

Everything above this (FastAPI, the eval harness, the CLI) calls ask() and
nothing else. Everything below it (retriever, generator, stores, providers) is an
implementation detail this class hides.

PII redaction wraps ask() -- it is NOT sprinkled into the layers below. Input is
scrubbed before retrieval/generation (so PII never reaches Pinecone, a hosted
LLM, or a log); output is scrubbed as a backstop before returning. Keeping the
scrub here, at the boundary, is what makes it impossible to bypass: there is no
path to the model that doesn't go through this method.

Redaction is toggleable (settings.pii_redaction) and fail-safe: if the redactor
can't be built, we FALL BACK TO REFUSING to process rather than silently sending
un-scrubbed text onward. A safety feature that silently disables itself is worse
than no safety feature, because you'd trust it.
"""

from __future__ import annotations

from config import settings
from src.generation.generator import Answer, Generator
from src.retrieval.retriever import Retriever


class Pipeline:
    def __init__(self, retriever: Retriever | None = None,
                 generator: Generator | None = None,
                 redactor=None) -> None:
        self.retriever = retriever or Retriever()
        self.generator = generator or Generator()

        # Build the redactor unless it's been disabled in config or injected
        # (tests inject a fake). If enabled but construction fails, we do NOT
        # silently continue unprotected -- self.redactor stays None and ask()
        # refuses. See the fail-safe branch below.
        self.redactor = redactor
        self._redaction_broken = False
        if redactor is None and settings.pii_redaction:
            try:
                from src.pii.redactor import Redactor
                self.redactor = Redactor()
            except Exception as e:
                self._redaction_broken = True
                self._redaction_error = str(e)

    def ask(self, question: str, k: int | None = None) -> Answer:
        pii_note = None

        if settings.pii_redaction:
            # Fail-safe: redaction was requested but the engine didn't build.
            # Refuse rather than leak. Better a broken feature that blocks than
            # one that silently passes PII to a third party.
            if self.redactor is None:
                return Answer(
                    text="PII redaction is enabled but unavailable, so I can't "
                         "safely process your message right now.",
                    abstained=True,
                    provider="",
                )
            red = self.redactor.redact(question)
            question = red.text            # everything downstream sees scrubbed text
            pii_note = red.warning()       # None unless PII was found

        # --- the existing spine, now operating on scrubbed input ---
        passages = self.retriever.search_or_abstain(question, k=k)
        answer = self.generator.answer(question, passages)

        # Output-side backstop: scrub the generated answer too.
        if settings.pii_redaction and self.redactor is not None and not answer.abstained:
            out = self.redactor.redact(answer.text)
            if out.found:
                answer.text = out.text

        # Prepend the user-facing PII warning (the "warn" in redact-and-warn).
        if pii_note:
            answer.text = f"{pii_note}\n\n{answer.text}"

        return answer


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