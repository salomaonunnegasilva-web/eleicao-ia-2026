#!/bin/sh
set -eu

uvicorn app.api.main:app --host 127.0.0.1 --port 8000 &
backend_pid=$!

cleanup() {
  kill "$backend_pid" 2>/dev/null || true
}
trap cleanup INT TERM EXIT

attempt=0
until curl --silent --fail http://127.0.0.1:8000/health >/dev/null; do
  attempt=$((attempt + 1))
  if [ "$attempt" -ge 30 ]; then
    echo "Backend failed to become healthy."
    exit 1
  fi
  sleep 1
done

streamlit run frontend/streamlit_app.py \
  --server.address=0.0.0.0 \
  --server.port="${PORT:-7860}" \
  --server.headless=true \
  --browser.gatherUsageStats=false
