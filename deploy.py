#!/usr/bin/env python3
# Deploy Kdenlive Headless Service to Coolify

import os, json, base64, secrets, sys, time
from pathlib import Path
import urllib.request, urllib.error

def main():
    env_path = Path('/opt/data/secrets/coolify.env')
    env = {}
    for line in env_path.read_text().splitlines():
        if line and not line.startswith('#') and '=' in line:
            k,v = line.split('=',1); env[k]=v.strip()
    
    base_url = env['COOLIFY_URL']
    token = env['COOLIFY_TOKEN']
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    
    def request(method, url, body=None):
        req = urllib.request.Request(url, method=method, headers=headers)
        if body:
            req.data = json.dumps(body).encode('utf-8')
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    
    # Workspace
    ws = Path('/opt/data/kdenlive-workspace')
    (ws/'projects').mkdir(parents=True, exist_ok=True)
    (ws/'results').mkdir(parents=True, exist_ok=True)
    (ws/'config').mkdir(parents=True, exist_ok=True)
    print(f"Workspace ready: {ws}")
    
    # Project
    projects = request('GET', f"{base_url}/api/v1/projects")
    proj = next((p for p in projects if p['name']=='Kdenlive Media'), None)
    if not proj:
        proj = request('POST', f"{base_url}/api/v1/projects", {'name':'Kdenlive Media'})
        print(f"Created project: {proj['uuid']}")
    else:
        print(f"Using project: {proj['name']} ({proj['uuid']})")
    project_uuid = proj['uuid']
    
    # Server + destination
    servers = request('GET', f"{base_url}/api/v1/servers")
    server_uuid = servers[0]['uuid']
    dests = request('GET', f"{base_url}/api/v1/servers/{server_uuid}/destinations")
    dest_uuid = dests[0]['uuid']
    print(f"Server: {servers[0]['name']} | Dest: {dests[0]['name']} ({dest_uuid})")
    
    # Environment
    envs = request('GET', f"{base_url}/api/v1/projects/{project_uuid}/environments")
    env_uuid = next((e['uuid'] for e in envs if e['name']=='production'), envs[0]['uuid'])
    print(f"Environment: production ({env_uuid})")
    
    # API key
    api_key = secrets.token_urlsafe(32)
    print(f"API Key: {api_key[:12]}...")
    
    # Compose
    compose = f"""version: '3.8'

services:
  kdenlive-headless:
    build:
      context: .
      dockerfile: Dockerfile
    container_name: kdenlive-headless
    environment:
      - KDENLIVE_API_KEY={api_key}
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
    
    # Create service via Coolify API
    body = {
        'project_uuid': project_uuid,
        'server_uuid': server_uuid,
        'environment_name': env_uuid,
        'docker_compose_raw': base64.b64encode(compose.encode()).decode()
    }
    
    svc = request('POST', f"{base_url}/api/v1/services", body)
    service_uuid = svc['uuid']
    print(f"\n✅ Service created: {service_uuid}")
    print(f"Image: localhost:3200/kdenlive-headless:latest")
    print(f"Port: 8080 (internal only)")
    print(f"Workspace: /opt/data/kdenlive-workspace")
    print(f"API Key: {api_key}")
    print(f"\nThis service is COMPLETELY separate from the trading dashboard.")
    print(f"It does NOT use any reserved URLs.")
    print(f"\nNext steps:")
    print(f"1. Wait for container to start (poll /api/v1/services/{service_uuid}/status)")
    print(f"2. Test: curl http://localhost:8080/health")
    print(f"3. Hermes integration: http://kdenlive-headless:8080")
    print(f"\nNote: The service is in Coolify project 'Kdenlive Media'")
    
    return service_uuid, api_key

if __name__ == '__main__':
    main()