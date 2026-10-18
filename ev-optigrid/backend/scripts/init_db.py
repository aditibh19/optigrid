"""
Fast local bring-up: creates all tables directly from the ORM models.

This is a convenience for local development only. The versioned, reviewable
schema history lives in Alembic migrations (`alembic/versions/`) — once
dependencies are installed, generate the real initial migration with:

    cd backend
    alembic revision --autogenerate -m "initial schema"
    alembic upgrade head

Run this script instead only when you want a disposable local DB fast:

    python scripts/init_db.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database.session import Base, engine
import models  # noqa: F401 — registers all tables


def main():
    print(f"Creating all tables on: {engine.url}")
    Base.metadata.create_all(bind=engine)
    print(f"Done. {len(Base.metadata.tables)} tables created:")
    for name in sorted(Base.metadata.tables.keys()):
        print(f"  - {name}")


if __name__ == "__main__":
    main()
