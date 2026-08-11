"""
main.py -- HTTP layer. Now with auth (Phase 4) and per-user history (Phase 5).

The two PHASE-5 placeholder lines from before are gone: /ask and /history now
depend on get_current_user, so they require a valid token and operate on the real
logged-in user. Adding one dependency turned them from open+placeholder into
login-only+per-user. That's the payoff of building the auth gate as a dependency.
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
from backend.models import User
from backend.auth_routes import router as auth_router, get_current_user

_pipeline: Pipeline | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _pipeline
    print("[api] building pipeline...")
    _pipeline = Pipeline()
    print(f"[api] ready. provider={settings.llm_provider} backend={settings.vector_backend}")
    yield
    print("[api] shutting down.")


app = FastAPI(title="Medical AI Health Assistant", version="0.3.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)

# mount the /auth/signup, /auth/login, /auth/me routes
app.include_router(auth_router)


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
def ask(
    req: AskRequest,
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),   # <- now requires login; gives us the user
) -> AskResponse:
    if _pipeline is None:
        raise HTTPException(status_code=503, detail="pipeline still starting")

    try:
        ans = _pipeline.ask(req.question, k=req.k)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"generation failed: {type(e).__name__}")

    # Phase 5: saved against the REAL logged-in user, not a placeholder.
    history_repo.save_exchange(db, user.id, req.question, ans.text)

    return AskResponse(
        answer=ans.text,
        abstained=ans.abstained,
        citations=[CitationOut(n=c.n, source=c.source, url=c.url or "") for c in ans.citations],
        provider=ans.provider,
    )


@app.get("/history", response_model=list[HistoryItem])
def history(
    db: Session = Depends(get_session),
    user: User = Depends(get_current_user),   # <- each user sees only their own
) -> list[HistoryItem]:
    rows = history_repo.get_history(db, user.id)
    return [
        HistoryItem(
            id=r.id, question=r.question, answer=r.answer,
            created_at=r.created_at.isoformat() if r.created_at else "",
        )
        for r in rows
    ]