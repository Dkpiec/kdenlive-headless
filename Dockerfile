# Kdenlive Headless - Dockerfile for Coolify (Git build source)
# Headless video rendering with FastAPI control API (melt / MLT backend)
FROM python:3.11-slim

# System dependencies.
# - kdenlive pulls in the MLT/melt engine + ffmpeg + x264/x265 codecs
# - libassimp5 / libmagickwand / libswscale / libvulkan are runtime libs melt may dlopen
ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get install -y --no-install-recommends \
    kdenlive \
    ffmpeg \
    melt \
    libmlt++7 \
    libassimp5 \
    libmagickwand-6.q16-6 \
    libswscale6 \
    libx264-163 \
    libx265-199 \
    libvulkan1 \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
RUN pip install --no-cache-dir \
    fastapi \
    uvicorn \
    pydantic \
    pydantic-settings

# Non-root user for security
RUN useradd -m -u 1000 -s /bin/bash render && \
    mkdir -p /workspace && \
    chown -R render:render /workspace

WORKDIR /workspace
COPY kdenlive_api.py entrypoint.sh /workspace/
RUN chmod +x /workspace/entrypoint.sh && \
    chown render:render /workspace/kdenlive_api.py /workspace/entrypoint.sh

USER render

ENV QT_QPA_PLATFORM=offscreen
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

ENTRYPOINT ["/workspace/entrypoint.sh"]
