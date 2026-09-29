#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
[ -f venv/bin/activate ] && source venv/bin/activate
export PYTHONPATH=.
echo "Starting Competitor Promotion Intelligence Platform on http://${HOST:-127.0.0.1}:${PORT:-8000}..."
# Keep a single worker: scan status and the scheduler live inside the process.
exec uvicorn app.main:app --host "${HOST:-127.0.0.1}" --port "${PORT:-8000}" --workers 1
