"""
redactor.py -- detect and mask PII before it leaves the machine.

WHERE THIS SITS AND WHY IT MATTERS:
  The input redactor runs BEFORE the question is embedded, sent to Pinecone, sent
  to a hosted LLM (Anthropic/Gemini), or written to any log. That ordering is the
  entire protection: once text reaches a third party, redaction is too late. The
  scrub has to happen on-machine, first.

  A local Ollama model is on your machine -- but Pinecone and the hosted LLM
  providers are NOT, and logs persist. So we scrub regardless of provider; "it's
  local today" is not a safety guarantee you want to depend on.

WHAT IT DOES (the "redact + warn" policy you chose):
  - find PII spans with Presidio
  - replace each with a typed placeholder: <PERSON>, <DATE_TIME>, <PHONE_NUMBER>...
  - report WHAT was found (types + count) so the caller can warn the user
  It does not refuse. A worried user who overshares still gets helped; they're
  just told their details were removed first.

OUTPUT-SIDE USE:
  The same redactor runs on the generated answer as a backstop. The NIH corpus
  rarely contains personal data, but belt-and-braces: if anything ever leaked
  through retrieval, it doesn't reach the user.

DESIGN NOTE -- placeholder, not deletion:
  We replace "John Smith" with "<PERSON>", not "". Keeping a typed placeholder
  preserves the sentence's meaning for retrieval ("my son <PERSON> has..." still
  reads as a question about a child) while removing the identifying value. Blank
  deletion would mangle the query.
"""

from __future__ import annotations

from dataclasses import dataclass, field


# The PII types we scrub. Kept explicit (not "everything Presidio can find") so
# behaviour is predictable and testable, and so we don't over-redact medical
# terms that a broad config might mistake for entities.
DEFAULT_ENTITIES = [
    "PERSON",
    "EMAIL_ADDRESS",
    "PHONE_NUMBER",
    "US_SSN",
    "CREDIT_CARD",
    "DATE_TIME",          # catches dates of birth
    "LOCATION",
    "MEDICAL_LICENSE",
    "MEDICAL_RECORD_NUMBER",   # custom -- see Redactor._add_mrn_recognizer
    "US_DRIVER_LICENSE",
    "IP_ADDRESS",
    "US_PASSPORT",
]


@dataclass
class RedactionResult:
    text: str                                   # the scrubbed text (safe to send onward)
    found: bool                                 # did we detect any PII?
    entity_types: list[str] = field(default_factory=list)   # e.g. ["PERSON", "US_SSN"]
    count: int = 0                              # how many spans were replaced

    def warning(self) -> str | None:
        """Human-facing notice for the 'warn' half of redact-and-warn. None when
        there's nothing to warn about."""
        if not self.found:
            return None
        types = ", ".join(t.replace("_", " ").lower() for t in self.entity_types)
        return (f"Note: I detected and removed personal information "
                f"({types}) from your message before processing it. "
                f"Please avoid sharing personal details.")


class Redactor:
    def __init__(self, entities: list[str] | None = None) -> None:
        # Import inside __init__ so importing this module doesn't require presidio
        # to be installed (keeps unit tests that stub the redactor dependency-free).
        try:
            from presidio_analyzer import AnalyzerEngine
        except ImportError as e:
            raise ImportError(
                "presidio-analyzer not installed. Run:\n"
                "  pip install presidio-analyzer presidio-anonymizer\n"
                "  python -m spacy download en_core_web_lg"
            ) from e

        try:
            self.analyzer = AnalyzerEngine()
        except Exception as e:
            # Almost always the missing spaCy model. Give the exact fix rather
            # than a raw stack trace.
            raise RuntimeError(
                "Presidio failed to start -- usually a missing spaCy model.\n"
                "Fix:  python -m spacy download en_core_web_lg"
            ) from e

        # Presidio's built-in US_SSN recognizer is conservative and, depending on
        # version, misses well-formed SSNs like "123-45-6789". An SSN has a rigid
        # shape, so we add an explicit high-confidence pattern for it. This is
        # PRECISE -- it fixes the specific gap without loosening global confidence
        # (which would fix the SSN by making the whole detector twitchier and
        # start producing false positives on phone numbers / dates).
        self._add_ssn_recognizer()

        # Presidio has NO concept of a medical record number -- it's a
        # domain-specific identifier. In a medical assistant it's exactly the kind
        # of PII you must catch, so we teach it the common MRN shapes explicitly.
        self._add_mrn_recognizer()

        self.entities = entities or DEFAULT_ENTITIES

    def _add_ssn_recognizer(self) -> None:
        from presidio_analyzer import Pattern, PatternRecognizer

        ssn_pattern = Pattern(
            name="ssn_flexible",
            # dashed, spaced, or bare 9-digit: 123-45-6789 / 123 45 6789 / 123456789
            regex=r"\b\d{3}[- ]?\d{2}[- ]?\d{4}\b",
            score=0.85,
        )
        ssn_recognizer = PatternRecognizer(
            supported_entity="US_SSN",
            patterns=[ssn_pattern],
            context=["ssn", "social", "security"],
        )
        self.analyzer.registry.add_recognizer(ssn_recognizer)

    def _add_mrn_recognizer(self) -> None:
        from presidio_analyzer import Pattern, PatternRecognizer

        mrn_pattern = Pattern(
            name="mrn",
            # "MRN 88213", "MRN-0044718", "MRN: 12345" -- the MRN prefix plus digits.
            # Requiring the prefix keeps it precise: bare numbers aren't flagged.
            regex=r"\bMRN[-:\s]?\d{4,10}\b",
            score=0.9,
        )
        mrn_recognizer = PatternRecognizer(
            supported_entity="MEDICAL_RECORD_NUMBER",
            patterns=[mrn_pattern],
            context=["mrn", "record", "patient", "medical"],
        )
        self.analyzer.registry.add_recognizer(mrn_recognizer)

    def redact(self, text: str, language: str = "en") -> RedactionResult:
        if not text or not text.strip():
            return RedactionResult(text=text, found=False)

        results = self.analyzer.analyze(
            text=text, entities=self.entities, language=language
        )
        if not results:
            return RedactionResult(text=text, found=False)

        # Presidio can return overlapping spans (e.g. our custom SSN pattern and a
        # built-in one both matching). Drop lower-scored overlaps so we don't
        # double-replace the same characters.
        results = self._dedupe_overlaps(results)

        # Replace spans right-to-left so earlier indices stay valid as we mutate.
        results = sorted(results, key=lambda r: r.start, reverse=True)
        scrubbed = text
        seen_types = []
        for r in results:
            placeholder = f"<{r.entity_type}>"
            scrubbed = scrubbed[:r.start] + placeholder + scrubbed[r.end:]
            seen_types.append(r.entity_type)

        # De-dupe types for the warning, but count every span replaced.
        ordered_unique = list(dict.fromkeys(reversed(seen_types)))
        return RedactionResult(
            text=scrubbed,
            found=True,
            entity_types=ordered_unique,
            count=len(results),
        )

    @staticmethod
    def _dedupe_overlaps(results):
        """Keep the highest-scored span when two overlap on the same characters.

        Without this, our custom SSN pattern and a built-in recognizer could both
        match the same digits, and we'd replace them twice, producing garbage like
        <US_SSN><US_SSN>.
        """
        chosen = []
        for r in sorted(results, key=lambda x: x.score, reverse=True):
            if any(not (r.end <= c.start or r.start >= c.end) for c in chosen):
                continue          # overlaps an already-kept, higher-scored span
            chosen.append(r)
        return chosen