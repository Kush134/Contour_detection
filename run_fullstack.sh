#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

cd "$ROOT_DIR"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
pip install -r requirements.txt

cd "$ROOT_DIR/frontend"
if [[ ! -d node_modules ]]; then
  npm install
fi

cd "$ROOT_DIR"
uvicorn backend.app:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

cleanup() {
  kill "$BACKEND_PID" >/dev/null 2>&1 || true
}
trap cleanup EXIT

cd "$ROOT_DIR/frontend"
npm run dev -- --host 0.0.0.0 --port 5173
