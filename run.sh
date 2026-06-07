#!/usr/bin/env bash
# run.sh — build the frontend (if needed) and start the app.
#   ./run.sh           normal run
#   ./run.sh dev       frontend hot-reload (run uvicorn separately)
set -e

if [ "$1" = "dev" ]; then
  echo "Starting Vite dev server (proxies API+WS to :8800). Run uvicorn separately."
  npm --prefix web install
  npm --prefix web run dev
  exit 0
fi

if [ ! -d "web/dist" ]; then
  echo "Building frontend..."
  npm --prefix web install
  npm --prefix web run build
fi
UVICORN="uvicorn"
[ -x ".venv/bin/uvicorn" ] && UVICORN=".venv/bin/uvicorn"
echo "Starting server at http://localhost:8800"
$UVICORN server.app:app --reload --port 8800
