"""
generator.py — turn retrieved passages into a grounded, cited answer.
 
Mirrors the stores.py pattern exactly: a Protocol, concrete providers, a factory
that reads config. Heavy client libraries import lazily inside each provider, so
importing this module never requires anthropic / google-genai / the ollama
package to be installed, and the tests run with none of them.
 
    LLM_PROVIDER=anthropic  -> Claude Haiku      (hosted, for the deployed demo)
    LLM_PROVIDER=gemini     -> Gemini Flash       (hosted, alternate)
    LLM_PROVIDER=ollama     -> local model        (no API cost, for dev + eval loops)
 
THE LOAD-BEARING LINE IN THIS FILE:
 
    if not passages:
        return Answer(text=REFUSAL_TEXT, ..., abstained=True)
 
When retrieval finds nothing above threshold, the LLM is never called. The model
is not asked to be honest and trusted to comply -- it is not given the chance to
answer at all. This holds identically across all three providers because the
check sits above them, in Generator.answer(), not inside any provider.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Protocol

from config import settings
from backend.generation.prompts import REFUSAL_TEXT, SYSTEM_PROMPT, build_user_prompt
from backend.retrieval.stores import Passage


@dataclass
class Citation:
    n: int          # the [n] label the model emitted
    source: str
    url: str
    question: str   # the MedQuAD question this passage answered


@dataclass
class Answer:
    text: str
    citations: list[Citation] = field(default_factory=list)
    passages: list[Passage] = field(default_factory=list)
    abstained: bool = False
    provider: str = ""


# ----------------------------------------------------------------------------
# providers  —  each exposes .name and .complete(system, user) -> str
# ----------------------------------------------------------------------------

class LLMProvider(Protocol):
    name: str
    def complete(self, system: str, user: str) -> str: ...


class AnthropicProvider:
    name = "anthropic"

    def __init__(self) -> None:
        import anthropic
        self.client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    def complete(self, system: str, user: str) -> str:
        resp = self.client.messages.create(
            model=settings.anthropic_model,
            max_tokens=settings.max_tokens,
            temperature=settings.temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(b.text for b in resp.content if b.type == "text")


class GeminiProvider:
    name = "gemini"

    def __init__(self) -> None:
        from google import genai
        from google.genai import types
        self._types = types
        self.client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])

    def complete(self, system: str, user: str) -> str:
        resp = self.client.models.generate_content(
            model=settings.gemini_model,
            contents=user,
            config=self._types.GenerateContentConfig(
                system_instruction=system,
                max_output_tokens=settings.max_tokens,
                temperature=settings.temperature,
            ),
        )
        return resp.text or ""


class OllamaProvider:
    """Local model served by the Ollama daemon (default http://localhost:11434).

    No API key, no per-token cost — this is the provider you develop and run the
    eval loop against. Two things worth knowing:

    * Ollama has no separate `system` role in its /api/chat the way the hosted
      APIs do, but it accepts a messages list with a role="system" entry, which
      we use so the grounding contract is delivered the same way everywhere.
    * `stream=False` so we get one complete JSON object back. `options.temperature`
      and `num_predict` (Ollama's name for max output tokens) mirror the hosted
      providers so switching LLM_PROVIDER doesn't silently change decoding.
    """
    name = "ollama"

    def __init__(self) -> None:
        # Lazy import: the `ollama` pip package is only needed for this provider.
        import ollama
        # host is configurable so a deployed container can point at a sidecar.
        self.client = ollama.Client(host=settings.ollama_host)
        self.model = settings.ollama_model

    def complete(self, system: str, user: str) -> str:
        resp = self.client.chat(
            model=self.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            stream=False,
            options={
                "temperature": settings.temperature,
                "num_predict": settings.max_tokens,
            },
        )
        return resp["message"]["content"]


def get_provider() -> LLMProvider:
    p = settings.llm_provider
    if p == "anthropic":
        return AnthropicProvider()
    if p == "gemini":
        return GeminiProvider()
    if p == "ollama":
        return OllamaProvider()
    raise ValueError(
        f"unknown llm_provider: {p!r} (use 'anthropic', 'gemini', or 'ollama')"
    )


# ----------------------------------------------------------------------------
# generator
# ----------------------------------------------------------------------------

_CITE_RE = re.compile(r"\[(\d+)\]")


class Generator:
    def __init__(self, provider: LLMProvider | None = None) -> None:
        self.provider = provider or get_provider()

    def answer(self, question: str, passages: list[Passage]) -> Answer:
        # ---- the safety property ----
        # Empty passage list means retrieval scored below settings.min_retrieval_score.
        # We refuse here, in Python, before any model sees the question. Holds for
        # every provider because the check is above the provider, not inside it.
        if not passages:
            return Answer(
                text=REFUSAL_TEXT,
                abstained=True,
                provider=self.provider.name,
            )

        raw = self.provider.complete(
            system=SYSTEM_PROMPT,
            user=build_user_prompt(question, passages),
        )

        return Answer(
            text=raw.strip(),
            citations=self._resolve_citations(raw, passages),
            passages=passages,
            abstained=False,
            provider=self.provider.name,
        )

    @staticmethod
    def _resolve_citations(text: str, passages: list[Passage]) -> list[Citation]:
        """Map the [n] labels the model emitted back onto real passage metadata.

        Out-of-range labels are dropped rather than trusted: the model can only
        *reference* a passage we gave it, so it can never fabricate a source or a
        URL. That is the whole reason citations are numbers and not free text.
        This matters more with a local 8B model than with a frontier one -- a
        smaller model is likelier to emit a stray [5], and this silently discards it.
        """
        seen: list[Citation] = []
        for m in _CITE_RE.finditer(text):
            n = int(m.group(1))
            if not (1 <= n <= len(passages)):
                continue                       # hallucinated label -> discard
            if any(c.n == n for c in seen):
                continue                       # already recorded
            p = passages[n - 1]
            seen.append(Citation(n=n, source=p.source, url=p.url, question=p.question))
        return sorted(seen, key=lambda c: c.n)