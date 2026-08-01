#!/bin/bash
set -e

# Start metrics uvicorn on port 9100 in background
uvicorn app.main:metrics_app --host 0.0.0.0 --port 9100 &
METRICS_PID=$!

# Start main application uvicorn on port 8000 in foreground
trap "kill $METRICS_PID 2>/dev/null || true" EXIT
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
