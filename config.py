"""
config.py — single source of truth for the whole system.

Mirrors the pattern from your FAS project: every module imports paths,
model names, and thresholds from here. Nothing hard-coded downstream.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
INDEX_DIR = DATA_DIR / "chroma"          # persisted vector store lives here
RAW_CORPUS = DATA_DIR / "medquad.csv"    # CSV with answers (see README data note)

# ---- MedQuAD raw download: set this once, here ----
# Point it at the GitHub ZIP (no need to extract) or an extracted folder.
#   Local:  DATA_DIR / "MedQuAD-master.zip"
#   Colab:  Path("/content/drive/MyDrive/medquad/MedQuAD-master.zip")
MEDQUAD_SRC = DATA_DIR 

EVAL_DIR = ROOT / "eval"


@dataclass(frozen=True)
class Settings:
    # ---- retrieval / embedding ----
    embed_model: str = "BAAI/bge-small-en-v1.5"   # 384-dim, CPU-f  riendly
    embed_dim: int = 384                           # must match embed_model
    collection_name: str = "medquad"
    top_k: int = 4                                 # passages retrieved per query
    chunk_chars: int = 1200                        # ~answers are long; chunk them
    chunk_overlap: int = 150

    # ---- vector store backend ----
    # "chroma" (local, reproducible — use for eval) | "pinecone" (hosted — use for demo)
    vector_backend: str = field(default_factory=lambda: os.getenv("VECTOR_BACKEND", "chroma"))
    pinecone_index: str = "medquad"
    pinecone_cloud: str = "aws"
    pinecone_region: str = "us-east-1"             # Starter tier is us-east-1 only

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
