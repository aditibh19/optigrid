> **Quickest route: `RUN_ON_YOUR_LAPTOP.md`** (one-command setup for Windows, macOS and Linux). This file is the manual reference.

# Setup

## Prerequisites

- Python 3.11+
- Node.js 18+
- PostgreSQL 14+ (optional for local dev — SQLite works out of the box)

## Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env
# Leave provider values as "demo" to run without any API keys (DEMO MODE).
# For a quick local DB, either:
#   (a) SQLite — set DATABASE_URL=sqlite:///./evoptigrid.db in .env, or
#   (b) Postgres — create a DB matching DATABASE_URL in .env.example

# Generate the versioned initial migration from the models (source of truth):
alembic revision --autogenerate -m "initial schema"
alembic upgrade head

# OR, for a disposable dev DB without migration history:
# python scripts/init_db.py

uvicorn main:app --reload
# → http://localhost:8000/health
# → http://localhost:8000/docs   (OpenAPI)
```

## Frontend

```bash
cd frontend
npm install
npm run dev      # http://localhost:3000 (start the backend first)
npm run e2e      # optional: live check of the API client against the running stack
# → http://localhost:3000
```

## Running tests

```bash
cd backend && pip install -r requirements.txt   # includes pytest
cd ..
pytest
```

The suite is 289 backend tests across `tests/optimization/`, `tests/ml/`,
`tests/simulation/` and `tests/backend/` (including
`tests/backend/test_api_endpoints.py`, which drives every FastAPI endpoint
against a throwaway SQLite DB). All 190 pass under real `pytest` 8.3 on
Python 3.12 with the versions pinned in `backend/requirements.txt`.

There's also a standalone, human-readable demo you can run without pytest
at all:

```bash
python optimization/demo_sdp.py
```

It solves the SDP for all 5 built-in profiles and prints a walkthrough:
convergence, profile-vs-profile divergence on the same state, a forward
simulation showing the policy deferring charging to a cheaper period, and
an infeasible-deadline case.

## Notes on dependencies

- `bcrypt` is pinned to `4.0.1` on purpose: `passlib 1.7.4` (unmaintained)
  breaks against `bcrypt >= 4.1` and registration/login would crash.
- `email-validator` is required by pydantic's `EmailStr` (auth schemas).
- The backend has been run against **SQLite only**. PostgreSQL is the
  intended production DB and the models use a native `UUID` there, but that
  path has not been exercised yet — run the pytest suite and the alembic
  steps against Postgres once (`DATABASE_URL` in `.env`) before relying on it.
