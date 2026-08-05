"""
judge.py — measure faithfulness without RAGAS, without LangChain, without a
hosted API. Just your Ollama client and two prompts.

FAITHFULNESS, the metric that matters most for a medical RAG:

    faithfulness = (claims supported by the passages) / (total claims)

It answers the one question a medical system lives or dies on: when it states
something, is that statement backed by a retrieved source, or did the model make
it up? A score of 1.0 means every claim traces to context; 0.6 means 40% of what
it said was ungrounded -- which for medicine is a failure regardless of whether
the ungrounded parts happen to be true.

Two-step, exactly what RAGAS does under the hood:

  1. DECOMPOSE  -- break the answer into atomic factual claims.
  2. VERIFY     -- for each claim, ask the judge: supported by these passages? y/n.

The judge is a SEPARATE model from the generator (qwen judging llama's output), so
the grader is not marking its own homework. Judge output is constrained to tiny,
parseable responses (a JSON list; then yes/no) precisely so we never have to trust
free-form text -- and so a thinking-trace, if one ever appears, can't corrupt the
score.

We also compute ANSWER RELEVANCY cheaply: did the answer actually address the
question, or wander? Faithfulness catches hallucination; relevancy catches
evasion. A system can be perfectly faithful and useless (refusing everything).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from config import settings


# ----------------------------------------------------------------------------
# judge model client  (Ollama, separate model from the generator)
# ----------------------------------------------------------------------------

class JudgeLLM:
    def __init__(self, model: str | None = None) -> None:
        import ollama
        self.client = ollama.Client(host=settings.ollama_host)
        self.model = model or settings.judge_model

    def ask(self, prompt: str) -> str:
        resp = self.client.chat(
            model=self.model,
            messages=[{"role": "user", "content": prompt}],
            stream=False,
            options={"temperature": 0.0},   # judgments must be deterministic
        )
        return resp["message"]["content"].strip()


# ----------------------------------------------------------------------------
# thinking-trace guard
# ----------------------------------------------------------------------------

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)

def _strip_thinking(text: str) -> str:
    """Belt-and-braces: qwen answered cleanly in testing, but if a future model
    or a longer prompt ever triggers a <think> block, drop it before parsing so
    it can never leak into a score."""
    return _THINK_RE.sub("", text).strip()


# ----------------------------------------------------------------------------
# prompts
# ----------------------------------------------------------------------------

_DECOMPOSE_PROMPT = """Break the following answer into a list of simple, \
self-contained factual claims. Each claim should state exactly one fact and be \
understandable on its own.

Return ONLY a JSON array of strings. No preamble, no markdown, no explanation.

Answer:
\"\"\"{answer}\"\"\"

JSON array of claims:"""


_VERIFY_PROMPT = """You are checking whether a claim is supported by reference \
passages. A claim is Supported ONLY if the passages directly state or clearly \
imply it. If the passages do not contain the information, it is Not Supported -- \
even if you personally believe the claim is true.

Reference passages:
\"\"\"{context}\"\"\"

Claim:
\"\"\"{claim}\"\"\"

Answer with exactly one word: Supported or Unsupported."""


_RELEVANCY_PROMPT = """Does the following answer address the question that was \
asked? Answer with exactly one word: Yes or No.

Question: {question}
Answer: {answer}

One word:"""


# ----------------------------------------------------------------------------
# result container
# ----------------------------------------------------------------------------

@dataclass
class FaithfulnessResult:
    question: str
    faithfulness: float             # 0..1, or -1 when not scored (see `status`)
    relevancy: int                  # 1 addressed / 0 did not
    n_claims: int
    n_supported: int
    claims: list[str] = field(default_factory=list)
    unsupported_claims: list[str] = field(default_factory=list)
    abstained: bool = False
    # WHY this field exists: three different things all produce faithfulness = -1,
    # and blending them silently corrupts the reported mean. We must tell them apart:
    #   "scored"       -- normal, faithfulness is a real 0..1 number
    #   "abstained"    -- retrieval gate refused; nothing generated to judge
    #   "no_claims"    -- the answer honestly said "sources don't cover this"
    #                     (a correct refusal in prose -> genuinely 0 claims)
    #   "parse_fail"   -- the JUDGE failed to extract claims from an answer that
    #                     HAS them. This is an eval bug, not system behaviour, and
    #                     it must be visible so it can't quietly bias the average.
    status: str = "scored"


# ----------------------------------------------------------------------------
# the judge
# ----------------------------------------------------------------------------

class FaithfulnessJudge:
    def __init__(self, llm: JudgeLLM | None = None) -> None:
        self.llm = llm or JudgeLLM()

    def _decompose(self, answer: str) -> tuple[list[str], bool]:
        """Return (claims, parse_ok).

        parse_ok is False only when the model produced output we could not turn
        into claims at all -- that flag is what lets run_eval distinguish a real
        judge failure from a legitimately claim-free answer, instead of silently
        dropping the question from the average.
        """
        raw = _strip_thinking(self.llm.ask(_DECOMPOSE_PROMPT.format(answer=answer)))

        # Primary: pull a JSON array out, even if wrapped in ```json fences or prose.
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        if m:
            try:
                claims = json.loads(m.group(0))
                cleaned = [c.strip() for c in claims
                           if isinstance(c, str) and c.strip()]
                if cleaned:
                    return cleaned, True
            except json.JSONDecodeError:
                pass  # fall through to the line-based fallback

        # Fallback: the model ignored the JSON instruction (common on smaller
        # local models) and wrote a bulleted or numbered list instead. Salvage it
        # rather than throwing the whole question away.
        lines = []
        for ln in raw.splitlines():
            ln = ln.strip()
            ln = re.sub(r"^[\-\*\u2022]\s*", "", ln)   # bullet markers
            ln = re.sub(r"^\d+[\.\)]\s*", "", ln)       # "1. " / "1) "
            if len(ln) > 8 and not ln.lower().startswith(("here", "json", "claim")):
                lines.append(ln)
        if lines:
            return lines, True

        # Genuinely nothing usable came back -> signal a parse failure.
        return [], False

    def _verify(self, claim: str, context: str) -> bool:
        out = _strip_thinking(
            self.llm.ask(_VERIFY_PROMPT.format(context=context, claim=claim))
        ).lower()
        # "supported" contains "support"; guard against "unsupported" matching first.
        return "unsupported" not in out and "support" in out

    def _relevant(self, question: str, answer: str) -> int:
        out = _strip_thinking(
            self.llm.ask(_RELEVANCY_PROMPT.format(question=question, answer=answer))
        ).lower()
        return 1 if out.startswith("y") else 0

    def score(self, question: str, answer: str, passages: list,
              abstained: bool = False) -> FaithfulnessResult:
        # An abstention is not a faithfulness failure -- refusing when there's no
        # evidence is CORRECT behaviour. Mark it and exclude from the faithfulness
        # mean, or you'd punish the system for its single best safety feature.
        if abstained:
            return FaithfulnessResult(
                question=question, faithfulness=-1.0, relevancy=1,
                n_claims=0, n_supported=0, abstained=True, status="abstained",
            )

        context = "\n\n".join(p.text for p in passages)
        claims, parse_ok = self._decompose(answer)

        if not claims:
            # Two very different reasons we're here -- keep them apart:
            if not parse_ok:
                # The judge couldn't parse an answer that likely HAS claims.
                # Flag it loudly; do not let it vanish into the average.
                status = "parse_fail"
            else:
                # The answer genuinely made no factual claim -- typically an
                # honest "the sources don't cover this". Correct behaviour.
                status = "no_claims"
            return FaithfulnessResult(
                question=question, faithfulness=-1.0,
                relevancy=self._relevant(question, answer),
                n_claims=0, n_supported=0, status=status,
            )

        supported, unsupported = 0, []
        for c in claims:
            if self._verify(c, context):
                supported += 1
            else:
                unsupported.append(c)

        return FaithfulnessResult(
            question=question,
            faithfulness=supported / len(claims),
            relevancy=self._relevant(question, answer),
            n_claims=len(claims),
            n_supported=supported,
            claims=claims,
            unsupported_claims=unsupported,
        )