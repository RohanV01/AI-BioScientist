#!/usr/bin/env bash
# Launch the In-Silico Drug Discovery Studio (FastAPI bridge + React SPA).
#
#   ./scripts/run_studio.sh          serve the built SPA + API on :8000 (one process)
#   ./scripts/run_studio.sh dev      API on :8000 + Vite dev server on :5173 (hot reload)
#
# Prereqs: Python deps in ./.venv, Node deps installed in ./frontend (npm install).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
MODE="${1:-prod}"

if [ "$MODE" = "dev" ]; then
  echo "▶ API   : http://localhost:8000  (uvicorn --reload)"
  echo "▶ Studio: http://localhost:5173  (Vite dev server, hot reload)"
  .venv/bin/uvicorn src.api.main:app --reload --port 8000 &
  API_PID=$!
  trap 'kill $API_PID 2>/dev/null || true' EXIT
  npm run dev --prefix frontend
else
  if [ ! -d frontend/dist ]; then
    echo "No frontend build found — building once…"
    npm install --prefix frontend
    npm run build --prefix frontend
  fi
  echo "▶ Studio: http://localhost:8000"
  .venv/bin/uvicorn src.api.main:app --port 8000
fi
