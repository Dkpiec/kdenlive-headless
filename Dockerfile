# Kdenlive Headless - Complete Dockerfile for Coolify
# Headless video rendering with FastAPI control API
FROM python:3.11-slim

# Install kdenlive, melt, ffmpeg and dependencies
RUN apt-get update && apt-get install -y \
    kdenlive \
    melt \
    ffmpeg \
    libassimpython \
    libimagemagick1 \
    libavcodec-extra \
    libswscale \
    libx264 \
    libx265 \
    libvulkan \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn \
    pydantic \
    pydantic-settings

# Create non-root user for security
RUN useradd -m -u 1000 -s /bin/bash render && \
    mkdir -p /workspace && \
    chown -R render:render /workspace

# Copy application files
WORKDIR /workspace
COPY kdenlive_api.py /workspace/
COPY entrypoint.sh /workspace/
RUN chmod +x /workspace/entrypoint.sh && chown render:render /workspace/kdenlive_api.py /workspace/entrypoint.sh

# Switch to non-root user
USER render

# Set QT platform for headless rendering
ENV QT_QPA_PLATFORM=offscreen

# Expose port 8080
EXPOSE 8080

# Health check - FastAPI /health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run entrypoint (starts FastAPI API server)
ENTRYPOINT ["/workspace/entrypoint.sh"]