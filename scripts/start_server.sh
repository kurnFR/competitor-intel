#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/.."
[ -f venv/bin/activate ] && source venv/bin/activate
export PYTHONPATH=.
# Refuse to start on a database that does not match this version (it would only show "Internal Server Error").
# Set AUTO_MIGRATE=true to upgrade it automatically instead (back up first on a real database).
if ! python -m scripts.check_schema; then
  if [ "${AUTO_MIGRATE:-false}" = "true" ]; then
    echo "AUTO_MIGRATE=true: upgrading the database..."
    alembic upgrade head
  else
    echo "Not starting. Fix the above (or set AUTO_MIGRATE=true) and run this script again." >&2
    exit 1
  fi
fi
echo "Starting Competitor Promotion Intelligence Platform on http://${HOST:-127.0.0.1}:${PORT:-8000}..."
# Keep a single worker: the scheduler, scan status and login throttling live in the process.
exec uvicorn app.main:app --host "${HOST:-127.0.0.1}" --port "${PORT:-8000}" --workers 1
