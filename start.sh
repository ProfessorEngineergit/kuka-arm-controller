#!/bin/bash
# Start the KUKA-ARM controller
APP_DIR="/home/pi/kuka-arm"
cd "$APP_DIR"

source venv/bin/activate
export $(grep -v '^#' .env | xargs)

PORT="${PORT:-80}"

exec uvicorn app.main:app \
  --host 0.0.0.0 \
  --port "$PORT" \
  --workers 1 \
  --log-level info
