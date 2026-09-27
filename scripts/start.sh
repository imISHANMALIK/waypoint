#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ] || [ ! -f frontend/dist/index.html ]; then
  echo 'Run ./scripts/setup.sh first.' >&2
  exit 1
fi
args=()
if [ -f .env ]; then args+=(--env-file .env); fi
exec .venv/bin/python -m uvicorn backend.app.main:app --host 127.0.0.1 --port "${PORT:-8000}" "${args[@]}"
