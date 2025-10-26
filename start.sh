#!/bin/bash
# Railway startup script - handles PORT env var expansion

# Railway provides PORT env var, default to 8000 if not set
PORT=${PORT:-8000}

echo "Starting uvicorn on port $PORT..."

# Start the FastAPI application
exec uvicorn backend.main:app --host 0.0.0.0 --port $PORT

