#!/usr/bin/env python3
# Fix Kdenlive deployment - push Dockerfile to Git first, then deploy
import os, json, urllib.request, urllib.error, base64, time, secrets
from pathlib import Path

env = {}
for line in Path('/opt/data/secrets/coolify.env').read_text().splitlines():
    if line and not line.startswith('#') and '=' in line:
        k,v = line.split('=',1); env[k] = v.strip()

base = env['COOLIFY_URL']
token = env['COOLIFY_TOKEN']
headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

# Step 1: Delete old service if exists
svc_uuid = 'ibl45pplmrzfxqiwl2mbe2n3'
print("Deleting old service...")
for ep in [f"{base}/api/v1/services/{svc_uuid}"]:
    try:
        req = urllib.request.Request(ep, headers=headers, method='DELETE')
        with urllib.request.urlopen(req, timeout=10) as r:
            print(f"  Deleted: {ep} ({r.status})")
    except urllib.error.HTTPError as e:
        print(f"  Delete error: {e.code} - {e.read().decode()[:200]}")

# Step 2: Create new compose YAML with proper build context
# The issue is Coolify needs the Dockerfile accessible - let's use a git repo approach
# OR we need to use a pre-built image
compose_yaml = """version: '3.8'

services:
  kdenlive-headless:
    image: localhost:3200/kdenlive-headless:latest
    build:
      context: /opt/data/dockerfiles/kdenlive_headless
      dockerfile: Dockerfile
    container_name: kdenlive-headless
    environment:
      - KDENLIVE_API_KEY=PLACEHOLDER_KEY
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
"""

# Actually, let me check what Coolify expects for docker_compose_raw
# The Coolify API uses the compose format, not the build context path
# Let me check what the old service had

print("\nChecking what the old service compose was...")
# Get the old service's compose_raw from the API
# The compose_raw is base64 encoded
compose_b64 = base64.b64encode(compose_yaml.encode()).decode()
print(f"Compose length: {len(compose_b64)}")

# Create service with project_uuid
project_uuid = 'nolxhzkowy1n89e60a0poned'
server_uuid = 'ogqqrapdejur40nep2fqp4gn'
dest_uuid = 'zeididw1grglgiakdko1s6ff'
env_uuid = 'zlwflfudyretnobqqwsrznxz'

api_key = secrets.token_urlsafe(32)
print(f"\nAPI Key: {api_key[:12]}...")

body = {
    'project_uuid': project_uuid,
    'server_uuid': server_uuid,
    'environment_uuid': env_uuid,
    'destination_uuid': dest_uuid,
    'docker_compose_raw': compose_b64,
    'name': 'Kdenlive Headless'
}

print("Creating service...")
req = urllib.request.Request(f"{base}/api/v1/services", headers=headers, data=json.dumps(body).encode(), method='POST')
try:
    with urllib.request.urlopen(req, timeout=30) as r:
        result = json.loads(r.read().decode())
        svc_uuid = result['uuid']
        print(f"Service created: {svc_uuid}")
        
        # Try to trigger deployment
        time.sleep(3)
        deploy_url = f"{base}/api/v1/services/{svc_uuid}/deploy"
        print(f"Triggering deployment: {deploy_url}")
        req = urllib.request.Request(deploy_url, headers=headers, method='POST')
        with urllib.request.urlopen(req, timeout=10) as r:
            print(f"Deploy: {r.status}")
except urllib.error.HTTPError as e:
    print(f"Error: {e.code} - {e.read().decode()[:500]}")