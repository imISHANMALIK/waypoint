#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -x .venv/bin/python ]; then
  if [ -z "${PYTHON_BIN:-}" ]; then
    for candidate in python3.13 python3.12 python3.11 python3; do
      if command -v "$candidate" >/dev/null && "$candidate" -c 'import sys; assert sys.version_info >= (3,11)' 2>/dev/null; then
        PYTHON_BIN="$candidate"
        break
      fi
    done
  fi
  if [ -z "${PYTHON_BIN:-}" ]; then
    echo 'Python 3.11+ is required. Install it, or set PYTHON_BIN to its executable.' >&2
    exit 1
  fi
  "$PYTHON_BIN" -m venv .venv
fi
.venv/bin/python -m pip install -r backend/requirements.lock
npm --prefix frontend ci --no-audit --no-fund
npm --prefix frontend run build
.venv/bin/python scripts/mcp_config.py > mcp.local.json
echo 'Waypoint is ready. Run ./scripts/start.sh and open http://127.0.0.1:8000'
