#!/usr/bin/env bash
# Starts the backend (port 8000) and the frontend (port 3000):  ./start.sh   (Ctrl+C stops both)
set -euo pipefail
cd "$(dirname "$0")"
[ -x backend/.venv/bin/python ] || { echo "Not set up yet. Run ./setup.sh first."; exit 1; }
[ -d frontend/node_modules ] || { echo "Frontend packages missing. Run ./setup.sh first."; exit 1; }

( cd backend && exec .venv/bin/python -m uvicorn main:app --port 8000 ) &
BACKEND_PID=$!
trap 'kill "$BACKEND_PID" 2>/dev/null || true' EXIT INT TERM

echo "Backend starting on http://localhost:8000 (API docs: http://localhost:8000/docs)"
echo "Frontend starting on http://localhost:3000  <- open this in your browser"
cd frontend && npm run dev
