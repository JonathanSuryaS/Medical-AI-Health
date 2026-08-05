"""
test_generation.py — prove the generation layer's contract without an index,
without API keys, and without downloading a model.
 
    pytest tests/test_generation.py -v
 
The point of the fakes is that the *safety property* is testable in isolation.
If someone later "optimises" the abstention branch away, this suite goes red in
under a second -- you do not need a live Pinecone index to catch it.
"""

from __future__ import annotations
 
import pytest
 
from src.generation.generator import Answer, Generator
from src.generation.prompts import REFUSAL_TEXT, build_user_prompt
from pipeline import Pipeline
from src.retrieval.stores import Passage
 
 
# ---------------------------------------------------------------- fakes
 
class FakeProvider:
    """Records what it was asked, returns a canned answer. Never hits a network."""
    name = "fake"
 
    def __init__(self, reply: str = "AAT deficiency causes shortness of breath [1]."):
        self.reply = reply
        self.calls: list[tuple[str, str]] = []
 
    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        return self.reply
 
 
class FakeRetriever:
    def __init__(self, passages: list[Passage]):
        self.passages = passages
 
    def search_or_abstain(self, query: str, k=None) -> list[Passage]:
        return self.passages
 
 
def _p(text: str, source: str = "NHLBI", url: str = "https://nhlbi.nih.gov/x") -> Passage:
    return Passage(text=text, source=source, question="What is AAT?", score=0.8, url=url)
 
 
# ---------------------------------------------------------------- the safety property
 
def test_empty_passages_abstains_without_calling_the_llm():
    """The single most important test in the repo.
 
    Retrieval found nothing above threshold -> we must refuse, and the model must
    never be given the chance to answer from parametric memory.
    """
    prov = FakeProvider()
    ans = Generator(provider=prov).answer("what is the capital of France?", [])
 
    assert ans.abstained is True
    assert ans.text == REFUSAL_TEXT
    assert ans.citations == []
    assert prov.calls == [], "LLM was called despite empty retrieval — abstention bypassed"
 
 
def test_pipeline_propagates_abstention_end_to_end():
    pipe = Pipeline(retriever=FakeRetriever([]), generator=Generator(provider=FakeProvider()))
    ans = pipe.ask("who won the world cup?")
    assert ans.abstained is True
 
 
# ---------------------------------------------------------------- happy path
 
def test_passages_produce_a_cited_answer():
    prov = FakeProvider()
    passages = [_p("Shortness of breath is a symptom."), _p("Emphysema may develop.")]
    ans = Generator(provider=prov).answer("symptoms of AAT?", passages)
 
    assert ans.abstained is False
    assert len(prov.calls) == 1
    assert [c.n for c in ans.citations] == [1]
    assert ans.citations[0].url == "https://nhlbi.nih.gov/x"
 
 
def test_passages_are_actually_put_in_the_prompt():
    """Guards against the classic RAG bug: retrieving, then not using the result."""
    passages = [_p("Cirrhosis is a rare complication.")]
    user = build_user_prompt("tell me about AAT", passages)
    assert "Cirrhosis is a rare complication." in user
    assert "[1]" in user
 
 
# ---------------------------------------------------------------- citation integrity
 
def test_hallucinated_citation_labels_are_discarded():
    """Model cites [7] but we only gave it 2 passages. We must not fabricate a source."""
    prov = FakeProvider(reply="This is true [1] and also this [7].")
    passages = [_p("a"), _p("b")]
    ans = Generator(provider=prov).answer("q", passages)
 
    assert [c.n for c in ans.citations] == [1], "out-of-range citation was not dropped"
 
 
def test_repeated_citations_are_deduplicated():
    prov = FakeProvider(reply="Claim one [1]. Claim two [1]. Claim three [2].")
    ans = Generator(provider=prov).answer("q", [_p("a"), _p("b")])
    assert [c.n for c in ans.citations] == [1, 2]
 
 
def test_every_citation_maps_to_a_real_passage():
    prov = FakeProvider(reply="[1] [2]")
    passages = [_p("a", source="NIDDK"), _p("b", source="NINDS")]
    ans = Generator(provider=prov).answer("q", passages)
 
    sources = {c.source for c in ans.citations}
    assert sources == {"NIDDK", "NINDS"}
    assert all(c.url for c in ans.citations), "citation lost its URL — provenance broken"