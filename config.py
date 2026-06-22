from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
INDEX_DIR = DATA_DIR / "chroma"          # persisted vector store lives here
RAW_CORPUS = DATA_DIR / "medquad.csv"    # CSV with answers (see README data note)
# Raw MedQuAD download. Point this at the GitHub .zip OR an extracted folder.
# Default assumes you dropped the downloaded zip into data/.
MEDQUAD_SRC = DATA_DIR / "MedQuAD-master.zip"
EVAL_DIR = ROOT / "eval"


@dataclass(frozen=True)
class Settings:
    # ---- retrieval / embedding ----
    embed_model: str = "BAAI/bge-small-en-v1.5"   # 384-dim, CPU-friendly
    collection_name: str = "medquad"
    top_k: int = 4                                 # passages retrieved per query
    chunk_chars: int = 1200                        # ~answers are long; chunk them
    chunk_overlap: int = 150

    # ---- generation ----
    # provider is read from env so you can swap without touching code.
    # supported: "anthropic" | "gemini"
    llm_provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "anthropic"))
    anthropic_model: str = "claude-haiku-4-5-20251001"
    gemini_model: str = "gemini-2.0-flash"
    max_tokens: int = 700
    temperature: float = 0.0                        # grounding wants determinism

    # ---- thresholds (your proposal's target metrics) ----
    faithfulness_target: float = 0.90
    context_recall_target: float = 0.85
    guardrail_catch_target: float = 0.95
    pii_redaction_target: float = 0.95

    # abstention: if best retrieval score is below this, refuse + refer
    min_retrieval_score: float = 0.30


settings = Settings()
