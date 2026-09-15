# Kdenlive Headless - Minimal Dockerfile for Coolify
# This is a simplified version focused on headless rendering
FROM python:3.11-slim

# Install kdenlive and necessary dependencies
RUN apt-get update && apt-get install -y \
    kdenlive \
    ffmpeg \
    libassimpython \
    libimagemagick1 \
    libavcodec-extra \
    libswscale \
    libx264 \
    libx265 \
    libvulkan \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /workspace

# Copy the Kdenlive application
COPY kdenlive /workspace/

# Expose port 8080 (Kdenlive default)
EXPOSE 8080

# Health check - Kdenlive exposes /health endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Run Kdenlive in headless mode
CMD ["kdenlive", "--mode=headless", "--port=8080"]
