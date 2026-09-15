#!/usr/bin/env python3
# Test Kdenlive API directly

import os, json, base64
from pathlib import Path
import urllib.request, urllib.error, time

print("=== Kdenlive API Test ===\n")

# Get API key
env = {}
for line in Path('/opt/data/secrets/coolify.env').read_text().splitlines():
    if line and not line.startswith('#') and '=' in line:
        k,v=line.split('=',1); env[k]=v.strip()

api_key = os.environ.get('KDENLIVE_API_KEY')
if not api_key:
    # Read from compose file if env var not set
    compose_file = Path('/opt/data/dockerfiles/kdenlive_headless/docker-compose.coolify.yml')
    if compose_file.exists():
        content = compose_file.read_text()
        # Try to extract API key
        import re
        match = re.search(r'KDENLIVE_API_KEY=(\S+)', content)
        if match:
            api_key = match.group(1)
            print(f"Found API key from compose file: {api_key[:10]}...")

if not api_key:
    # Check if there's an env file
    env_file = Path('/opt/data/dockerfiles/kdenlive_headless/.env')
    if env_file.exists():
        env_content = env_file.read_text()
        match = re.search(r'KDENLIVE_API_KEY=(\S+)', env_content)
        if match:
            api_key = match.group(1)

print(f"API Key: {api_key[:10] if api_key else 'NOT FOUND'}...\n")

# Test endpoints
api_url = 'http://localhost:8080'
print(f"Testing API at: {api_url}\n")

# Health check
try:
    print("1. Health check:")
    req = urllib.request.Request(f"{api_url}/health")
    with urllib.request.urlopen(req, timeout=10) as resp:
        print(f"   Status: {resp.status}")
        print(f"   Body: {resp.read().decode()[:200] if resp.read() else 'Empty'}")
except urllib.error.HTTPError as e:
    print(f"   Health check failed: {e.code}")
except Exception as e:
    print(f"   Connection failed: {e}")

print("\n2. Project list:")
try:
    req = urllib.request.Request(f"{api_url}/projects")
    with urllib.request.urlopen(req, timeout=10) as resp:
        print(f"   Status: {resp.status}")
        print(f"   Projects: {len(json.loads(resp.read()).get('projects', []))}")
except Exception as e:
    print(f"   Failed: {e}")

print("\n3. Status:")
try:
    req = urllib.request.Request(f"{api_url}/status")
    with urllib.request.urlopen(req, timeout=10) as resp:
        print(f"   Status: {resp.status}")
        print(f"   Body: {resp.read().decode()[:500] if resp.read() else 'Empty'}")
except Exception as e:
    print(f"   Failed: {e}")

print("\n=== Test Complete ===")
PYEOF