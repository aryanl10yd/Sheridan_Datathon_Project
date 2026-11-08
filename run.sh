#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
PYTHON="${PYTHON:-.venv/bin/python}"
INTELLIGENCE_PORT="${SENTINEL_INTELLIGENCE_PORT:-8000}"
INTERLOCK_PORT="${SENTINEL_INTERLOCK_PORT:-8001}"
PORT="${PORT:-3000}"
env -u GRANITE_API_KEY -u OPENAI_API_KEY "$PYTHON" -m uvicorn app.approval_service:app --host 127.0.0.1 --port "$INTERLOCK_PORT" &
INTERLOCK_PID=$!
env -u DEMO_PIN_ALICE -u DEMO_PIN_BOB -u SENTINEL_DEVICE_SECRET \
  "$PYTHON" -m uvicorn app.main:app --host 127.0.0.1 --port "$INTELLIGENCE_PORT" &
INTELLIGENCE_PID=$!
cleanup() { kill "$INTERLOCK_PID" "$INTELLIGENCE_PID" 2>/dev/null || true; }
trap cleanup EXIT INT TERM
env -u DEMO_PIN_ALICE -u DEMO_PIN_BOB -u SENTINEL_DEVICE_SECRET -u GRANITE_API_KEY -u OPENAI_API_KEY \
  "$PYTHON" -m uvicorn app.gateway:app --host "${HOST:-127.0.0.1}" --port "$PORT"
