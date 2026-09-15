#!/bin/bash
# Kdenlive Headless - Entrypoint Script
# Starts the FastAPI API server

cd /workspace

# Set environment variables
export QT_QPA_PLATFORM=offscreen
export PATH="/usr/local/bin:$PATH"

# Start the FastAPI API server
exec uvicorn kdenlive_api:app \
    --host 0.0.0.0 \
    --port 8080 \
    --log-level info