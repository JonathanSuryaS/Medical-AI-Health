"""
main.py — HTTP layer over the pipeline. The "deployed inference" Must-Have.

    uvicorn src.api.main:app --reload
    -> interactive docs at http://localhost:8000/docs

This file is deliberately THIN. It does exactly three things: validate the
request, call Pipeline.ask(), shape the response. All the intelligence --
retrieval, the abstention gate, generation, citations -- lives below, in
Pipeline. If this file ever grows real logic, that logic is in the wrong place.

Why that matters for the demo defence: "the API is a thin wrapper over the same
Pipeline object my eval harness tests" is a strong sentence. It means the thing
you serve is the exact thing you measured -- no divergence between the evaluated
system and the deployed one.

The Pipeline is built ONCE at startup (see lifespan), not per request. Building
it per request would reload the embedding model and re-open the vector store on
every call -- seconds of latency per question. One warm instance, reused.
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from config import settings
from backend.pipeline import Pipeline

_pipeline: Pipeline | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: build the pipeline once. Warms the embedder and opens the vector
    # store, so the first real request isn't paying that cost.
    global _pipeline
    print("[api] building pipeline (loads embedder + opens vector store)...")
    _pipeline = Pipeline()
    print(f"[api] ready. provider={settings.llm_provider} backend={settings.vector_backend}")
    yield
    print("[api] shutting down.")


app = FastAPI(
    title="Medical AI Health Assistant",
    description="RAG over NIH/NLM medical sources, with grounded citations and "
                "an abstention gate that refuses when retrieval is weak.",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS: open for now so a local Streamlit/HTML frontend on another port can call
# this during development. TIGHTEN before deploy -- replace "*" with the real
# frontend origin, or anyone's browser page can call your API.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["POST", "GET"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------- schemas

class AskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000,
                          description="The medical question to answer.")
    k: int | None = Field(None, ge=1, le=20,
                          description="Passages to retrieve. Defaults to config top_k.")


class CitationOut(BaseModel):
    n: int
    source: str
    url: str


class AskResponse(BaseModel):
    answer: str
    abstained: bool = Field(..., description="True if the system refused (weak retrieval).")
    citations: list[CitationOut]
    provider: str


# ---------------------------------------------------------------- routes

@app.get("/health")
def health() -> dict:
    """Liveness probe. Deploy platforms (Render/Railway) ping this. Also a quick
    way to confirm the pipeline actually finished building."""
    return {
        "status": "ok" if _pipeline is not None else "starting",
        "provider": settings.llm_provider,
        "backend": settings.vector_backend,
    }


@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    if _pipeline is None:
        raise HTTPException(status_code=503, detail="pipeline still starting")
    try:
        ans = _pipeline.ask(req.question, k=req.k)
    except Exception as e:
        # Don't leak internals to the caller; generic message, log server-side.
        raise HTTPException(status_code=500, detail=f"generation failed: {type(e).__name__}")

    return AskResponse(
        answer=ans.text,
        abstained=ans.abstained,
        citations=[CitationOut(n=c.n, source=c.source, url=c.url or "") for c in ans.citations],
        provider=ans.provider,
    )