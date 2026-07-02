#!/bin/sh
set -e

# FastAPI stays internal-only (127.0.0.1) — never exposed on Railway's $PORT.
cd /app/backend
uvicorn app.main:app --host 127.0.0.1 --port 8000 &
API_PID=$!

# Forward SIGTERM from Railway to the API process too, then exit.
trap 'kill $API_PID 2>/dev/null' TERM INT

for i in $(seq 1 30); do
  if curl -sf http://127.0.0.1:8000/health > /dev/null 2>&1; then
    break
  fi
  sleep 1
done

# SvelteKit Node server is the sole process bound to Railway's public $PORT.
cd /app/frontend
exec node build
