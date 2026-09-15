# Kdenlive Headless - Deploy with Coolify

This directory contains the complete setup for deploying Kdenlive as a headless rendering service in Coolify.

## Current State

- **Workspace**: `/opt/data/kdenlive-workspace` (projects/, results/, config/)
- **Existing Coolify Service**: `kdenlive-media` (uuid: `s0d8f8mcwoncwj8jh1s3uyty`) - STUCK at "starting:unknown"
- **New Recommended Architecture**: Custom headless service with FastAPI API

## Problems with Current Setup

The existing `kdenlive-media` service:
- Uses GUI image: `lscr.io/linuxserver/kdenlive:latest`
- Exposed ports: `3000:3000`, `3001:3001` (unused)
- Stuck at "starting:unknown" - likely crash-looping

## Recommended Fix

### Option 1: Fix Existing Service

Use `coolify-operations` skill to:
1. Get current service details: `GET /api/v1/services/s0d8f8mcwoncwj8jh1s3uyty`
2. Replace the compose with the new headless setup
3. Restart service

### Option 2: Create New Service

Deploy the headless version from `docker-compose.coolify.yml`:
- Uses API image with FastAPI on port 8080
- Separate workspace at `/opt/data/kdenlive-workspace`
- Internal-only access (no public ngrok needed)

## Docker Compose (Headless)

```yaml
services:
  kdenlive-headless:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: kdenlive-headless
    image: localhost:3200/kdenlive-headless:latest
    environment:
      - KDENLIVE_API_KEY=${KDENLIVE_API_KEY}
      - TZ=Asia/Kolkata
    volumes:
      - /opt/data/kdenlive-workspace:/workspace
    ports:
      - "8080"
    restart: unless-stopped
    networks:
      - hermesnet
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s

networks:
  hermesnet:
    name: gw5navcuqga1qhxypunyvhya
    external: true
```

## Hermes Integration

Hermes connects to the internal API:

```bash
# Submit render job
curl -X POST http://kdenlive-headless:8080/submit_render_job \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "project_path=/workspace/projects/my_video.mlt" \
  -d "output_name=output.mp4" \
  -d "fps=30" \
  -d "resolution=1920x1080" \
  -d "api_key=$KDENLIVE_API_KEY"

# Check status
curl http://kdenlive-headless:8080/job_status/{job_id}?api_key=$KDENLIVE_API_KEY
```

## Key Benefits

- **Headless**: No GUI overhead
- **Internal API**: Secure REST API on port 8080
- **Isolated**: Separate from trading dashboard
- **Share**: Same workspace accessible to both containers
- **Monitored**: Health checks and job tracking

## Next Steps

1. Choose Option 1 (fix existing) or Option 2 (new service)
2. Use the `coolify-operations` skill to deploy with proper API calls
3. Verify service is healthy using the test script
4. Configure Hermes to use the API endpoint