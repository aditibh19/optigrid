#!/usr/bin/env bash
# One-time setup for macOS / Linux:  ./setup.sh
set -euo pipefail
cd "$(dirname "$0")"

echo "== Checking Python (need 3.10, 3.11 or 3.12)"
PY="${PYTHON:-python3}"
command -v "$PY" >/dev/null || { echo "Python not found. Install Python 3.12 from https://www.python.org/downloads/"; exit 1; }
"$PY" -c 'import sys; sys.exit(0 if (3,10) <= sys.version_info[:2] <= (3,12) else 1)' || {
  echo "Found $("$PY" --version). This project needs Python 3.10, 3.11 or 3.12 (the pinned NumPy/SciPy have no wheels for 3.13+)."
  echo "Install 3.12, then run:  PYTHON=python3.12 ./setup.sh"; exit 1; }

echo "== Checking Node.js (need 18 or newer)"
command -v node >/dev/null || { echo "Node.js not found. Install the LTS version from https://nodejs.org/"; exit 1; }
node -e 'process.exit(Number(process.versions.node.split(".")[0]) >= 18 ? 0 : 1)' || { echo "Node $(node -v) is too old. Install Node 20 or 22 LTS."; exit 1; }

echo "== Backend: virtual environment + packages (first time takes a few minutes)"
[ -d backend/.venv ] || "$PY" -m venv backend/.venv
backend/.venv/bin/python -m pip install --quiet --upgrade pip
backend/.venv/bin/python -m pip install -r backend/requirements.txt

echo "== Backend: settings + local database"
[ -f backend/.env ] || cp backend/.env.example backend/.env
( cd backend && .venv/bin/python scripts/init_db.py )

echo "== Frontend: packages"
( cd frontend && npm install --no-audit --no-fund )

echo
echo "Setup complete. Start the app with:  ./start.sh   then open http://localhost:3000"
