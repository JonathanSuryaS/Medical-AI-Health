"""
db.py -- the single database connection for the whole backend.
 
WHAT THIS FILE IS
  One SQLAlchemy "engine" (the connection pool to NeonDB) and one "session
  factory" (how each request gets a short-lived conversation with the database).
  Every other file that touches the database imports from here -- the same
  one-source-of-truth idea as config.py, so there's never a second, divergent
  connection floating around.
 
WHY SQLALCHEMY AND NOT RAW SQL
  You chose the ORM. It lets you work with Python classes (a User object) instead
  of hand-writing SQL strings. Less error-prone, and it parameterizes queries for
  you, which closes off SQL-injection -- a real security win you get for free.
 
THE CONNECTION STRING NEVER LIVES HERE
  It's read from DATABASE_URL in .env. This file has no secret in it, so it's safe
  to commit. The secret stays on your machine.
"""


from __future__ import annotations
 
import os
 
from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker
 
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Add your Neon connection string to .env:\n"
        "  DATABASE_URL=postgresql://user:pass@host/dbname?sslmode=require"
    )
    

# psycopg (v3) is the driver. SQLAlchemy needs the URL to name it explicitly as
# postgresql+psycopg://... Neon hands you postgresql://..., so we normalise it.
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1 )
    

# The engine is the pool of connections to Neon. pool_pre_ping checks a connection
# is still alive before handing it out -- important with Neon, whose free tier can
# drop idle connections, which would otherwise surface as a random error mid-request.
engine = create_engine(DATABASE_URL, pool_pre_ping=True)

# Each request opens a Session (a unit of work), does its reads/writes, closes it.
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

# All ORM table classes will inherit from this Base (Phase 2 uses it).
Base = declarative_base()


def get_session():
    """FastAPI dependency: yields a session, guarantees it's closed afterwards.
    Used in Phase 3+ so each request gets its own clean database conversation."""
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
        

def check_connection() -> None:
    """Phase 1 smoke test: open a connection, run the most trivial query there is,
    confirm the round-trip works. `SELECT 1` touches no tables -- it only proves
    'can Python reach NeonDB and get an answer back'."""
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        value = result.scalar()
    print(f"[db] connected to NeonDB — SELECT 1 returned {value}")
 
 
if __name__ == "__main__":
    check_connection()
 