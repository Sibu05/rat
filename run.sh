#!/usr/bin/env bash
# RAT (Repo Analysis Tool) — one-command launcher.
# Usage: ./run.sh            (starts backend on http://127.0.0.1:8000)
#        PORT=9000 ./run.sh (different port)
set -euo pipefail
cd "$(dirname "$0")"

PORT="${PORT:-8000}"
PY=python3

echo "==> Checking Python dependencies"
$PY -m pip install -q -r backend/requirements.txt

if [ -d frontend/node_modules ] && [ ! -d frontend/dist ]; then
    echo "==> Building frontend"
    (cd frontend && npm run build)
fi

if [ -d frontend/dist ]; then
    echo "==> Serving dashboard + API on http://127.0.0.1:${PORT}"
else
    echo "==> Frontend not built yet — API only on http://127.0.0.1:${PORT}"
    echo "    (for the UI: cd frontend && npm install && npm run dev)"
fi

exec $PY -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT" --app-dir backend
