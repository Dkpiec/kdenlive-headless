#!/usr/bin/env python3
# Delete the old exited service and create a new one with proper build context
import os, json, urllib.request, urllib.error
from pathlib import Path

env = {}
for line in Path('/opt/data/secrets/coolify.env').read_text().splitlines():
    if line and not line.startswith('#') and '=' in line:
        k,v = line.split('=',1); env[k] = v.strip()

base = env['COOLIFY_URL']
token = env['COOLIFY_TOKEN']
headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

# Step 1: Delete the old exited service
svc_uuid = 'qr8spmr1vmwz5ho6plwdypnk'
app_uuid = '8cwmx8gkpiqg1rfhs2k5sl1u'

print("Step 1: Deleting old exited service...")
for endpoint in [f"{base}/api/v1/services/{svc_uuid}", f"{base}/api/v1/applications/{app_uuid}"]:
    try:
        req = urllib.request.Request(endpoint, headers=headers, method='DELETE')
        with urllib.request.urlopen(req, timeout=10) as r:
            print(f"  Deleted {endpoint}: {r.status}")
    except urllib.error.HTTPError as e:
        print(f"  Delete {endpoint}: {e.code} - {e.read().decode()[:200]}")

# Step 2: Read the Dockerfile
dockerfile_path = Path('/opt/data/dockerfiles/kdenlive_headless/Dockerfile')
dockerfile_content = dockerfile_path.read_text()
print(f"\nStep 2: Dockerfile ({len(dockerfile_content)} bytes)")

# Step 3: Read other files
api_file = Path('/opt/data/dockerfiles/kdenlive_headless/kdenlive_api.py')
api_content = api_file.read_text()
print(f"  kdenlive_api.py: {len(api_content)} bytes")

# Step 4: Create a base64-encoded docker-compose for Coolify
# Using the compose with build context pointing to a git repo or local dir
# Coolify needs the build context to be accessible - let's try with a local path
compose_yaml = """services:
  kdenlive-headless:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: kdenlive-headless
    environment:
      - KDENLIVE_API_KEY=REPLACE_ME
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
compose_b64 = base64.b64encode(compose_yaml.encode()).decode()
print(f"\nStep 3: Compose YAML encoded ({len(compose_b64)} bytes)")

# Step 5: Create a new Coolify service
project_uuid = 'nolxhzkowy1n89e60a0poned'
server_uuid = 'ogqqrapdejur40nep2fqp4gn'
dest_uuid = 'zeididw1grglgiakdko1s6ff'
env_uuid = 'zlwflfudyretnobqqwsrznxz'

import secrets
api_key = secrets.token_urlsafe(32)
print(f"\nStep 4: Generated API key: {api_key[:12]}...")

body = {
    'project_uuid': project_uuid,
    'server_uuid': server_uuid,
    'environment_uuid': env_uuid,
    'destination_uuid': dest_uuid,
    'docker_compose_raw': compose_b64,
    'name': 'Kdenlive Headless'
}

print("\nStep 5: Creating new service...")
try:
    req = urllib.request.Request(f"{base}/api/v1/services", headers=headers, data=json.dumps(body).encode(), method='POST')
    with urllib.request.urlopen(req, timeout=30) as r:
        result = json.loads(r.read().decode())
        new_svc_uuid = result['uuid']
        print(f"  Created service: {new_svc_uuid}")
except urllib.error.HTTPError as e:
    print(f"  Error: {e.code} - {e.read().decode()[:500]}")
    new_svc_uuid = None

# Step 6: Deploy
if new_svc_uuid:
    print(f"\nStep 6: Deploying service {new_svc_uuid}...")
    time.sleep(2)
    try:
        req = urllib.request.Request(f"{base}/api/v1/services/{new_svc_uuid}/deploy", headers=headers, method='POST')
        with urllib.request.urlopen(req, timeout=10) as r:
            print(f"  Deploy initiated: {r.status}")
    except urllib.error.HTTPError as e:
        print(f"  Deploy error: {e.code} - {e.read().decode()[:200]}")

print("\nDone! Service should be building.")
print(f"API endpoint will be: http://localhost:8080")
print(f"API Key: {api_key}")
