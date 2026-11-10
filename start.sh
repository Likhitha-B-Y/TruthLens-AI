#!/usr/bin/env bash
# TruthLens AI launcher for Linux / macOS
#   ./start.sh          set up (first run) and start the app at http://localhost:8000
#   ./start.sh dev      backend + Vite dev server with hot reload (needs Node.js), http://localhost:5173
#   ./start.sh models   download the AI models now (roughly 0.5-1 GB)
#   ./start.sh test     run the backend test-suite
#   ./start.sh setup    only create the virtual environment and install dependencies
set -euo pipefail
cd "$(dirname "$0")"
MODE="${1:-prod}"

PY="$(command -v python3 || command -v python || true)"
[ -z "$PY" ] && { echo "[ERROR] Python 3.10-3.12 is required."; exit 1; }

if [ ! -x .venv/bin/python ]; then
  echo "[1/3] Creating virtual environment in .venv ..."
  "$PY" -m venv .venv
fi
VPY=".venv/bin/python"

if [ ! -f .venv/.deps_installed ]; then
  echo "[2/3] Installing Python dependencies (several minutes the first time) ..."
  "$VPY" -m pip install --upgrade pip
  "$VPY" -m pip install -r backend/requirements.txt
  touch .venv/.deps_installed
fi

case "$MODE" in
  setup)  echo "Setup complete."; exit 0 ;;
  models) exec "$VPY" backend/scripts/download_models.py ;;
  test)   cd backend && exec "../$VPY" -m pytest -q ;;
  dev)
    command -v npm >/dev/null || { echo "[ERROR] Node.js is required for dev mode."; exit 1; }
    [ -d frontend/node_modules ] || (cd frontend && npm install)
    (cd backend && "../$VPY" -m uvicorn app.main:get_app --factory --reload --port 8000) &
    BACK=$!
    trap 'kill $BACK 2>/dev/null || true' EXIT
    cd frontend && npm run dev
    ;;
  *)
    if [ ! -f frontend/dist/index.html ]; then
      command -v npm >/dev/null || { echo "[ERROR] frontend/dist is missing and Node.js is not installed to build it."; exit 1; }
      echo "[3/3] Building the frontend ..."
      (cd frontend && npm install && npm run build)
    fi
    echo
    echo " TruthLens AI is starting at http://localhost:8000   (API docs: /docs)"
    echo " The first verification downloads the AI models once (roughly 0.5-1 GB)."
    echo
    cd backend && exec "../$VPY" -m uvicorn app.main:get_app --factory --host 127.0.0.1 --port 8000
    ;;
esac
