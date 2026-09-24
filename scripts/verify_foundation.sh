#!/usr/bin/env bash
set -euo pipefail

: "${DATABASE_URL:?DATABASE_URL must point to the clean competitor_intel database}"
export DATABASE_SCHEMA="${DATABASE_SCHEMA:-competitor_intel}"

echo "== Competitor Intel foundation verification =="
echo "Database schema: $DATABASE_SCHEMA"

alembic upgrade head
PYTHONPATH=. pytest -q tests/integration/test_postgres_schema.py

echo "== Reversibility check: downgrade to base =="
alembic downgrade base

echo "== Rebuild check: upgrade to head =="
alembic upgrade head
PYTHONPATH=. pytest -q tests/integration/test_postgres_schema.py

echo "Foundation database gate: PASS"
