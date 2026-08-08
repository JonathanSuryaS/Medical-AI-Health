"""
test_pii.py -- measure the PII redaction catch rate against a labelled set.

    pytest tests/test_pii.py -v -s

This produces your proposal's pii_redaction >= 0.95 number. ~30 cases spread
across the PII types real patients actually type, PLUS negative cases (clean
medical text that must NOT be redacted).

HOW TO READ A FAILURE: a failure is a real gap, not a broken test. When a case
fails, you decide -- fix it (add a custom recognizer, as we did for SSN/MRN) or
accept it and document the limitation. Do NOT delete a failing case to make the
number look better; that's hiding the gap, not closing it.

Some cases below are EXPECTED to be hard -- spaced/bare SSNs, unusual date
formats, non-Western names. They're here on purpose: a test set that only
contains easy wins proves nothing.
"""

from __future__ import annotations

import pytest

presidio = pytest.importorskip("presidio_analyzer")

from src.pii.redactor import Redactor


# ============================================================================
# POSITIVE CASES -- (text, entity types that MUST be caught)
# ============================================================================

POSITIVE_CASES = [
    # --- names: varied positions and forms ---
    ("My name is John Smith and I have a headache.", ["PERSON"]),
    ("Patient Maria Garcia reports fatigue.", ["PERSON"]),
    ("My daughter Sarah has had a fever for three days.", ["PERSON"]),
    ("Dr. Chen prescribed me something last week.", ["PERSON"]),
    ("I spoke to a nurse named Priya Patel about it.", ["PERSON"]),
    ("Is Kwame Osei's condition hereditary?", ["PERSON"]),          # non-Western name (harder)

    # --- dates, including DOB in several formats ---
    ("I'm 45, DOB 03/12/1980, with chest pain.", ["DATE_TIME"]),
    ("My son was born on March 12, 2015 and has asthma.", ["DATE_TIME"]),
    ("Symptoms started on January 3rd this year.", ["DATE_TIME"]),

    # --- email ---
    ("Email me results at jane.doe@gmail.com please.", ["EMAIL_ADDRESS"]),
    ("Contact: robert_wilson88@yahoo.co.uk for my chart.", ["EMAIL_ADDRESS"]),

    # --- phone, several formats ---
    ("Call me on 555-123-4567 about my test.", ["PHONE_NUMBER"]),
    ("My number is (555) 987 6543.", ["PHONE_NUMBER"]),
    ("Reach me at +1 555 111 2222 tomorrow.", ["PHONE_NUMBER"]),

    # --- SSN, several formats (spaced/bare are the hard ones) ---
    ("My SSN is 123-45-6789, am I eligible?", ["US_SSN"]),
    ("Social security 987 65 4321 on file.", ["US_SSN"]),           # spaced (harder)

    # --- medical record numbers (Presidio has NO built-in concept -> custom) ---
    ("Patient MRN 88213 needs a follow-up.", ["MEDICAL_RECORD_NUMBER"]),
    ("My medical record number is MRN-0044718.", ["MEDICAL_RECORD_NUMBER"]),

    # --- address ---
    ("I live at 123 Main Street, Boston MA 02101.", ["LOCATION"]),

    # --- credit card (insurance/billing context) ---
    ("Billing card 4111 1111 1111 1111 was declined.", ["CREDIT_CARD"]),

    # --- combinations: must catch ALL, not just one ---
    ("I'm Emily Brown, DOB 07/04/1990, reachable at 555-234-5678.",
     ["PERSON", "DATE_TIME", "PHONE_NUMBER"]),
    ("Contact David Kim at david.kim@mail.com or 555-333-1212.",
     ["PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER"]),
]


# ============================================================================
# NEGATIVE CASES -- clean medical text that must NOT be redacted
# The tricky ones: medical terms shaped like names/places, numbers that aren't PII.
# ============================================================================

NEGATIVE_CASES = [
    "What are the symptoms of type 2 diabetes?",
    "How is asthma treated in adults?",
    "What causes high blood pressure?",
    "Explain the stages of chronic kidney disease.",
    "Is stage 4 cancer always terminal?",
    "How many glasses of water should I drink a day?",
    "What is a normal blood pressure, is 120/80 healthy?",
    "Tell me about Lyme disease symptoms.",             # Lyme = a town (FP risk)
    "Is Still's disease a form of arthritis?",          # apostrophe-S like a surname
    "What is Bell's palsy and how long does it last?",  # same FP risk
    "Are German measles dangerous in pregnancy?",       # 'German' could trip LOCATION
]


# ============================================================================
# tests
# ============================================================================

@pytest.fixture(scope="module")
def redactor():
    try:
        return Redactor()
    except Exception as e:
        pytest.skip(f"Redactor unavailable (likely missing spaCy model): {e}")


@pytest.mark.parametrize("text,expected_types", POSITIVE_CASES)
def test_positive_pii_is_caught(redactor, text, expected_types):
    result = redactor.redact(text)
    assert result.found, f"missed ALL PII in: {text!r}"
    missed = [t for t in expected_types if t not in result.entity_types]
    assert not missed, (
        f"missed {missed} in {text!r} — caught only {result.entity_types}"
    )


@pytest.mark.parametrize("text", NEGATIVE_CASES)
def test_negative_clean_text_untouched(redactor, text):
    result = redactor.redact(text)
    assert not result.found, (
        f"FALSE POSITIVE: redacted clean text {text!r} as {result.entity_types}"
    )


def test_catch_rate_summary(redactor):
    """Prints the aggregate numbers you report. Asserts the 0.95 target so the
    suite goes red if a regression drops you below it."""
    # positives: count how many had ALL expected types caught
    fully_caught = 0
    partial = []
    for text, expected in POSITIVE_CASES:
        r = redactor.redact(text)
        if all(t in r.entity_types for t in expected):
            fully_caught += 1
        else:
            partial.append((text, expected, r.entity_types))

    recall = fully_caught / len(POSITIVE_CASES)

    false_pos = [t for t in NEGATIVE_CASES if redactor.redact(t).found]
    fp_rate = len(false_pos) / len(NEGATIVE_CASES)

    print(f"\n  PII catch rate (recall):   {recall:.1%}  "
          f"({fully_caught}/{len(POSITIVE_CASES)})  target 95%")
    print(f"  false-positive rate:       {fp_rate:.1%}  "
          f"({len(false_pos)}/{len(NEGATIVE_CASES)})  target 0%")
    if partial:
        print("\n  cases NOT fully caught (fix or document these):")
        for text, exp, got in partial:
            print(f"    want {exp} got {got}  <- {text[:55]}")
    if false_pos:
        print("\n  false positives (over-redaction):")
        for t in false_pos:
            print(f"    {t[:60]}")

    # The gate. Comment out while iterating if you want the summary to always
    # print; uncomment for CI / final reporting.
    assert recall >= 0.95, f"catch rate {recall:.1%} below 0.95 target"
    assert fp_rate == 0.0, f"false-positive rate {fp_rate:.1%} above 0% target"