"""
main.py -- HTTP layer over the pipeline, now with chat-history persistence.

New in Phase 3:
  - /ask saves each question+answer to the database after answering
  - GET /history returns saved history
  - a DB session is opened per request via the get_session dependency

Still deliberately thin. The pipeline does the thinking; the repo does the storage;
this file just wires request -> pipeline -> repo -> response.

Phase 3 uses a placeholder user (id=1) because there's no login yet. The two lines
marked PHASE-5 are the only ones that change when real auth arrives.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from config import settings
from backend.pipeline import Pipeline
from backend.db import get_session
from backend import history_repo

_pipeline: Pipeline | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pipeline
    print("[api] building pipeline...")
    _pipeline = Pipeline()
    print(f"[api] ready. provider={settings.llm_provider} backend={settings.vector_backend}")
    yield
    print("[api] shutting down.")


app = FastAPI(title="Medical AI Health Assistant", version="0.2.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------- schemas

class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)
    k: int | None = Field(None, ge=1, le=20)


class CitationOut(BaseModel):
    n: int
    source: str
    url: str


class AskResponse(BaseModel):
    answer: str
    abstained: bool
    citations: list[CitationOut]
    provider: str


class HistoryItem(BaseModel):
    id: int
    question: str
    answer: str
    created_at: str


# ---------------------------------------------------------------- routes

@app.get("/health")
def health() -> dict:
    return {"status": "ok" if _pipeline is not None else "starting"}


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest, db: Session = Depends(get_session)) -> AskResponse:
    if _pipeline is None:
        raise HTTPException(status_code=503, detail="pipeline still starting")

    try:
        ans = _pipeline.ask(req.question, k=req.k)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"generation failed: {type(e).__name__}")

    # --- Phase 3: persist the exchange ---
    # PHASE-5: replace these two lines with the real logged-in user's id.
    user_id = history_repo.ensure_placeholder_user(db)
    history_repo.save_exchange(db, user_id, req.question, ans.text)

    return AskResponse(
        answer=ans.text,
        abstained=ans.abstained,
        citations=[CitationOut(n=c.n, source=c.source, url=c.url or "") for c in ans.citations],
        provider=ans.provider,
    )


@app.get("/history", response_model=list[HistoryItem])
def history(db: Session = Depends(get_session)) -> list[HistoryItem]:
    # PHASE-5: replace with the real logged-in user's id.
    user_id = history_repo.ensure_placeholder_user(db)
    rows = history_repo.get_history(db, user_id)
    return [
        HistoryItem(
            id=r.id,
            question=r.question,
            answer=r.answer,
            created_at=r.created_at.isoformat() if r.created_at else "",
        )
        for r in rows
    ]