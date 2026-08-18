"""
init_db.py -- create the tables in NeonDB. Run once.

    py -m backend.init_db

SQLAlchemy reads every class that inherits from Base (User, ChatHistory) and
issues the CREATE TABLE statements for any that don't exist yet. Running it again
is safe -- it skips tables that already exist, so it never wipes your data.

This is fine for a project of this size. Bigger projects use "migrations" (tools
like Alembic) to evolve tables over time without losing data -- worth knowing the
word, not worth the overhead here.
"""

from backend.db import Base, engine

# Importing models registers the table classes on Base.metadata. Without this
# import, Base wouldn't know the tables exist and would create nothing.
from backend import models  # noqa: F401  (imported for its side effect)


def main() -> None:
    print("[init_db] creating tables (users, chat_history)...")
    Base.metadata.create_all(bind=engine)
    print("[init_db] done. Tables that now exist:")
    for table_name in Base.metadata.tables:
        print(f"  - {table_name}")


if __name__ == "__main__":
    main()