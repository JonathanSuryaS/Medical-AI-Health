# Medical AI Health Assistant

A retrieval-augmented question-answering system for consumer health questions. It
answers **only** from a curated corpus of NIH/NLM medical articles, cites its
sources inline, refuses when it has no grounded answer, and redacts personal
information before it ever leaves the machine.

Built for the INaAI 2026 AI Engineer track (NLP/LLM Agent domain).

---

## What it does

Ask a medical question, get an answer grounded in trusted sources — or an honest
refusal when the sources don't cover it.

```
Q: What are the symptoms of alpha-1 antitrypsin deficiency?

A: The signs and symptoms include shortness of breath following mild activity [1],
   wheezing [1][2], and recurring respiratory infections [1]...

   Sources:
   [1] GHR   — https://ghr.nlm.nih.gov/condition/alpha-1-antitrypsin-deficiency
   [2] NHLBI — https://www.nhlbi.nih.gov/health/health-topics/topics/aat
```

```
Q: Who won the 2022 World Cup?

A: [abstained] I don't have reliable sources covering that question, so I'm not
   going to guess. For medical questions I can't ground in a trusted source, the
   right next step is a qualified healthcare professional.
```

The second response is the point: the system is built so it **cannot answer
without a source**, rather than merely being asked not to.

---

## Design principles

**Grounding is enforced in code, not requested in a prompt.** When retrieval finds
no passage above the similarity threshold, the language model is never called at
all — the refusal happens in Python, before generation. A prompt instruction can
be ignored; an un-made API call cannot.

**Citations are verifiable.** The model emits only numeric labels (`[1]`, `[2]`)
that map back onto the retrieved passages. It never writes a source URL itself, so
a fabricated citation is structurally impossible — out-of-range labels are
discarded.

**PII never leaves the machine.** Personal information is detected and masked
*before* the question is embedded, sent to any hosted model, or written to a log.
Redaction wraps the pipeline at its boundary, so there is no code path to the
model that skips it.

**One spine, reused everywhere.** The API, the CLI, and the evaluation harness all
call the same `Pipeline.ask()` — so the system that gets measured is exactly the
system that gets served.

---

## Architecture

Two paths: an **offline** build (run once) and an **online** query path (per
question).

### Offline — build the index

```
MedQuAD XML  →  medquad.csv  →  chunks  →  embeddings  →  vector store
(12 folders)   (16.4k answered   (1200-char   (bge-small,   (Chroma / Pinecone)
               pairs; empties     overlap 150)  384-dim)
               dropped)
```

The three copyright-removed MedQuAD subsets (MedlinePlus/ADAM/Drugs/Herbs) have
empty answers; the ingestion script drops them and reports the count, so the
corpus can't be silently poisoned by blank passages.

### Online — answer a question

```
question
   ↓
[input gate]   PII redaction  (mask → warn)
   ↓
[retriever]    embed query → top-k passages
   ↓
   ├─ nothing above threshold → ABSTAIN (refuse + refer)
   ↓
[generator]    grounded, cited answer  (Ollama / Anthropic / Gemini)
   ↓
[output gate]  PII backstop
   ↓
answer + citations
```

---

## Project layout

```
config.py                     single source of truth (models, thresholds, paths)
src/
  pipeline.py                 the spine — Pipeline.ask()
  ingest/
    medquad_xml_to_csv.py     MedQuAD XML → flat CSV
    build_index.py            CSV → embeddings → vector store
  retrieval/
    embedder.py               bge-small, shared by index + query
    stores.py                 Chroma + Pinecone behind one interface
    retriever.py              embed query, top-k, abstention gate
  generation/
    generator.py              Ollama / Anthropic / Gemini behind one interface
    prompts.py                grounding + citation + refusal contract
  pii/
    redactor.py               Presidio + custom SSN/MRN recognizers
  api/
    main.py                   FastAPI — POST /ask
eval/
  run_eval.py                 sample → answer → judge → report
  judge.py                    LLM-as-judge faithfulness (no RAGAS dependency)
tests/
  test_generation.py          abstention + citation integrity
  test_pii.py                 PII catch rate vs a labelled set
```

---

## Setup

Requires Python 3.11 or 3.12 (not 3.13 — torch wheels).

```bash
python -m venv .venv
.venv\Scripts\activate           # Windows;  source .venv/bin/activate on macOS/Linux

pip install -r requirements.txt
python -m spacy download en_core_web_lg   # PII detection model
```

Create a `.env` in the project root:

```
LLM_PROVIDER=ollama              # ollama (local) | anthropic | gemini
VECTOR_BACKEND=chroma            # chroma (local) | pinecone (hosted)
PII_REDACTION=true

# only needed for the corresponding provider/backend:
ANTHROPIC_API_KEY=
GOOGLE_API_KEY=
PINECONE_API_KEY=
```

For the local default, install [Ollama](https://ollama.com) and pull the models:

```bash
ollama pull llama3.1:8b          # generator
ollama pull qwen3.5:9b           # eval judge
```

---

## Build the index

The corpus (`data/medquad.csv`) is derived from MedQuAD and built locally:

```bash
python -m src.ingest.medquad_xml_to_csv     # MedQuAD XML → data/medquad.csv
python -m src.ingest.build_index --reset    # CSV → vectors
```

Expect ~16,400 answered pairs → ~27,000 chunks.

---

## Run

**API**

```bash
uvicorn src.api.main:app --reload
# interactive docs at http://localhost:8000/docs
```

```bash
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What causes typhoid fever?"}'
```

**One-off from the CLI**

```bash
python -m src.pipeline "What are the symptoms of type 2 diabetes?"
```

---

## Evaluation

Faithfulness is measured with a local LLM-as-judge (no RAGAS/LangChain
dependency): each answer is decomposed into claims, and each claim is checked
against the retrieved passages. Faithfulness = supported claims / total claims.

```bash
python -m eval.run_eval --n 50
```

| metric | result | target |
|---|---|---|
| Faithfulness (scored subset) | strong on n=5 pilot; full run pending | 0.90 |
| PII catch rate | **95.5%** (21/22) | 0.95 |
| PII false-positive rate | **0%** (0/11) | 0% |

Test suites:

```bash
pytest tests/test_generation.py -v     # abstention + citation integrity (no API/index needed)
pytest tests/test_pii.py -v -s         # PII catch rate vs labelled set
```

---

## Current status

**Working**
- Retrieval + generation spine, with the abstention gate proven on both paths
- FastAPI endpoint with interactive docs
- PII redaction (input + output), 95.5% catch / 0% false positives
- LLM-as-judge evaluation harness
- Provider swap (Ollama / Anthropic / Gemini) and backend swap (Chroma / Pinecone)

**Deferred / in progress**
- **Guardrails** (emergency triage, injection defence) — scaffolded, not yet built
- **Deployment** — the codebase is deploy-ready (hosted-provider + Pinecone swap),
  but no public instance is running
- Evaluation parser has a known edge case on some judge outputs; the harness flags
  these as `parse_fail` rather than silently skewing the mean
- `top_k` and `min_retrieval_score` set to reasonable defaults; a full sweep against
  the eval set is pending

**Known limitations**
- International phone numbers in `+1 555 111 2222` spaced form are occasionally
  classified as `DATE_TIME` rather than `PHONE_NUMBER` — the value is still
  redacted, only the type label is wrong
- Faithfulness is measured on in-corpus questions, so retrieval scores optimistic;
  numbers are not held-out

---

## Data & attribution

Corpus derived from [MedQuAD](https://github.com/abachaa/MedQuAD) (Ben Abacha &
Demner-Fushman, 2019), sourced from NIH/NLM institutes (NCI, GARD, GHR, NIDDK,
NINDS, NHLBI, CDC, and others). Copyright-restricted subsets are excluded during
ingestion.

This system provides medical *information*, not medical *advice*. It does not
diagnose or prescribe, and it is not a substitute for a qualified healthcare
professional.
