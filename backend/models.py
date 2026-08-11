"""
models.py -- the database tables, defined as Python classes.
 
This is the ORM idea made concrete: each class here IS a table, each attribute IS
a column. SQLAlchemy translates between "a User object in Python" and "a row in the
users table in Postgres" so you rarely write raw SQL.
 
THE RELATIONSHIP IS THE POINT
  A User has many ChatHistory rows; each ChatHistory belongs to one User. That link
  is the ForeignKey below (chat_history.user_id -> users.id). It's what lets you ask
  "show me everything user #5 asked" and get back only their history -- the
  foundation of per-user data.
"""

from __future__ import annotations
 
from datetime import datetime
 
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
 
from backend.db import Base


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # unique=True: the database itself refuses a second row with the same email,
    # so you can't accidentally create duplicate accounts even with a race.
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    # This holds the HASH, never the raw password. The column name says so on purpose.
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
      DateTime(timezone=True), server_default=func.now()
    )
    
    # ORM convenience: user.history gives you all their ChatHistory rows as a list.
    # cascade="all, delete-orphan": if a user is deleted, their history goes too,
    # rather than leaving orphaned rows pointing at a user that no longer exists.
    history: Mapped[list["ChatHistory"]] = relationship(
      back_populates="user", cascade="all, delete-orphan"
    )


class ChatHistory(Base):
    __tablename__ = "chat_history"
 
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # THE FOREIGN KEY: this row belongs to the user with this id. The database
    # enforces that user_id must match a real users.id -- you can't save history
    # for a user who doesn't exist.
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
 
    # The other side of the relationship: history_row.user gives you the User object.
    user: Mapped["User"] = relationship(back_populates="history")
      