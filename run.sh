#!/usr/bin/env bash
set -e

echo "Starting FridgeSense backend & frontend with isolated venv..."

PYTHON_BIN="backend/venv/bin/python"
if [ ! -f "$PYTHON_BIN" ]; then
  echo "Virtual environment not found in backend/venv, creating..."
  python3 -m venv backend/venv
  backend/venv/bin/pip install -r backend/requirements.txt
fi

(cd backend && ./venv/bin/python seed.py && ./venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload) &
BACKEND_PID=$!

(cd frontend && npm run dev) &
FRONTEND_PID=$!

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null || true" EXIT

wait

