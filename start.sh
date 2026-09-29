#!/bin/bash
# Start the KUKA-ARM controller
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"

source venv/bin/activate
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

PORT="${PORT:-80}"

exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "$PORT" \
  --workers 1 \
  --log-level info
