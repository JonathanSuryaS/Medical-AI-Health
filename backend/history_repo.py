"""
history_repo.py -- the only file that reads/writes chat history.

"Repository" is just a name for "the layer that talks to one table". Isolating DB
access here (not scattering session.add() calls through your API) means: the API
stays about HTTP, this stays about storage, and if the table changes, one file
changes. Same separation-of-concerns habit as api.js on the frontend.

Phase 3 note: user_id is passed in. Right now the caller passes a placeholder (1);
in Phase 5 it'll pass the real logged-in user's id. This file doesn't change when
that happens -- it already takes whoever it's told. That's the point of building it
user-id-agnostic now.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import ChatHistory, User


def ensure_placeholder_user(db: Session) -> int:
    """Phase 3 scaffold: make sure a user with id=1 exists to attach history to,
    since there's no login yet. Returns the id. Removed once real auth lands."""
    user = db.get(User, 1)
    if user is None:
        user = User(
            id=1,
            email="placeholder@local",
            hashed_password="",   # not a real account; auth phase replaces this
        )
        db.add(user)
        db.commit()
    return 1


def save_exchange(db: Session, user_id: int, question: str, answer: str) -> ChatHistory:
    """Write one question+answer to the database. commit() is what actually
    persists it to Neon -- until commit, it's only pending in this session."""
    row = ChatHistory(user_id=user_id, question=question, answer=answer)
    db.add(row)
    db.commit()
    db.refresh(row)   # reload so row.id and row.created_at are populated
    return row


def get_history(db: Session, user_id: int, limit: int = 50) -> list[ChatHistory]:
    """Read back a user's history, newest first. This is the query that makes
    'my past chats' possible -- filter by user_id, so each person sees only theirs."""
    stmt = (
        select(ChatHistory)
        .where(ChatHistory.user_id == user_id)
        .order_by(ChatHistory.created_at.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt))