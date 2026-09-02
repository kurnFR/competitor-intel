#!/usr/bin/env bash
set -e
cd /home/BIS/competitor-intel
source venv/bin/activate
export PYTHONPATH=.
echo "Starting Competitor Promotion Intelligence Platform on http://0.0.0.0:8000..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
