#!/bin/sh
set -eu

ROOT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
cleanup() { kill "$API_PID" "$WEB_PID" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

cd "$ROOT_DIR/backend"
uv run uvicorn cost_data.main:app --reload --host 127.0.0.1 --port 8765 &
API_PID=$!
cd "$ROOT_DIR/frontend"
pnpm dev &
WEB_PID=$!
wait
