#!/usr/bin/env bash
set -euo pipefail
python -m pip install -r backend/requirements.lock
npm --prefix frontend ci --no-audit --no-fund
npm --prefix frontend run build
