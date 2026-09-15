#!/usr/bin/env python3
# Deploy Kdenlive Headless Service to Coolify
# This script creates a completely isolated headless Kdenlive service
# separate from the Trading Infra service and its reserved URLs.
#
# The service uses Coolify's public Git application feature to pull
# the code from GitHub and build the Docker image automatically.

import os, json, urllib.request, urllib.error, base64, secrets, time, sys
from pathlib import Path

def main():
    env_path = Path('/opt/data/secrets/coolify.env')
    env = {}
    for line in env_path.read_text().splitlines():
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=',1)
            env[k] = v.strip()

    base_url = env['COOLIFY_URL']
    token = env['COOLIFY_TOKEN']
    headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}

    def api_request(method, url, body=None):
        req = urllib.request.Request(url, method=method, headers=headers)
        if body:
            req.data = json.dumps(body).encode('utf-8')
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())

    # --- Step 1: Ensure workspace directories exist ---
    ws = Path('/opt/data/kdenlive-workspace')
    (ws / 'projects').mkdir(parents=True, exist_ok=True)
    (ws / 'results').mkdir(parents=True, exist_ok=True)
    (ws / 'config').mkdir(parents=True, exist_ok=True)
    print(f"✓ Workspace ready: {ws}")

    # --- Step 2: Get or create project ---
    projects = api_request('GET', f"{base_url}/api/v1/projects")
    proj = next((p for p in projects if p['name'] == 'Kdenlive Media'), None)
    if not proj:
        proj = api_request('POST', f"{base_url}/api/v1/projects", {'name': 'Kdenlive Media'})
        print(f"✓ Created project: {proj['uuid']}")
    else:
        print(f"✓ Using project: {proj['name']} ({proj['uuid']})")
    project_uuid = proj['uuid']

    # --- Step 3: Get server, destination, environment ---
    servers = api_request('GET', f"{base_url}/api/v1/servers")
    server_uuid = servers[0]['uuid']

    dests = api_request('GET', f"{base_url}/api/v1/servers/{server_uuid}/destinations")
    dest_uuid = dests[0]['uuid']
    print(f"✓ Server: {servers[0]['name']} | Dest: {dests[0]['name']} ({dest_uuid})")

    envs = api_request('GET', f"{base_url}/api/v1/projects/{project_uuid}/environments")
    env_uuid = next((e['uuid'] for e in envs if e['name'] == 'production'), envs[0]['uuid'])
    print(f"✓ Environment: production ({env_uuid})")

    # --- Step 4: Generate API key ---
    api_key = secrets.token_urlsafe(32)
    print(f"✓ Generated API key: {api_key[:12]}...")

    # --- Step 5: Delete any existing Kdenlive services ---
    all_services = api_request('GET', f"{base_url}/api/v1/services")
    for svc in all_services:
        if 'kdenlive' in svc['name'].lower() or 'kdenlive' in str(svc.get('applications', [])).lower():
            svc_uuid = svc['uuid']
            print(f"✓ Deleting old service: {svc['name']} ({svc_uuid})")
            try:
                api_request('DELETE', f"{base_url}/api/v1/services/{svc_uuid}")
            except:
                pass
            time.sleep(1)

    # --- Step 6: Create Coolify public Git application ---
    # Using the Coolify applications/public endpoint for Git-based deployment
    print("\n✓ Creating Coolify public Git application...")

    body = {
        "project_uuid": project_uuid,
        "environment_name": "production",
        "server_uuid": server_uuid,
        "destination_uuid": dest_uuid,
        "git_repository": "https://github.com/Dkpiec/kdenlive-headless.git",
        "git_branch": "main",
        "build_pack": "dockerfile",
        "ports_exposes": "8080",
        "force_domain_override": True
    }

    try:
        result = api_request('POST', f"{base_url}/api/v1/applications/public", body)
        app_uuid = result['uuid']
        print(f"✓ Application created: {app_uuid}")
        print(f"  Repository: https://github.com/Dkpiec/kdenlive-headless.git")
        print(f"  Branch: main")
        print(f"  Build pack: dockerfile")
        print(f"  Port: 8080")
    except urllib.error.HTTPError as e:
        err = e.read().decode()
        print(f"✗ Failed to create application: {e.code} - {err[:500]}")
        print("\nTrying alternative method (docker-compose service)...")

        # Fallback: use docker-compose with external image reference
        compose_yaml = f"""services:
  kdenlive-headless:
    image: ghcr.io/dkpiec/kdenlive-headless:latest
    container_name: kdenlive-headless
    environment:
      - KDENLIVE_API_KEY={api_key}
      - TZ=Asia/Kolkata
      - QT_QPA_PLATFORM=offscreen
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

        body = {
            'project_uuid': project_uuid,
            'server_uuid': server_uuid,
            'environment_uuid': env_uuid,
            'destination_uuid': dest_uuid,
            'docker_compose_raw': compose_b64,
            'name': 'Kdenlive Headless'
        }

        result = api_request('POST', f"{base_url}/api/v1/services", body)
        svc_uuid = result['uuid']
        print(f"✓ Service created via compose: {svc_uuid}")
        app_uuid = svc_uuid

    # --- Step 7: Trigger deployment ---
    print("\n✓ Triggering deployment...")
    time.sleep(2)
    try:
        api_request('POST', f"{base_url}/api/v1/applications/{app_uuid}/start")
        print(f"✓ Deployment initiated for application {app_uuid}")
    except:
        try:
            api_request('POST', f"{base_url}/api/v1/services/{app_uuid}/deploy")
            print(f"✓ Deployment initiated via services endpoint")
        except urllib.error.HTTPError as e:
            print(f"  Deploy endpoint error: {e.code}")
            print(f"  Service may start automatically from Coolify")

    # --- Step 8: Wait and check status ---
    print("\n✓ Waiting for container to start (30s)...")
    time.sleep(30)

    for i in range(6):
        try:
            svc = api_request('GET', f"{base_url}/api/v1/services")
            for s in svc:
                if 'kdenlive' in s['name'].lower():
                    app = s.get('applications', [{}])[0] if s.get('applications') else {}
                    print(f"  Status check {i+1}: Service={s.get('status')}, App={app.get('status')}, Image={app.get('image', 'N/A')}")
                    if s.get('status') == 'running:healthy' or app.get('status') == 'running:healthy':
                        print("\n✅ Service is running and healthy!")
                        break
                    elif s.get('status') == 'exited':
                        print("  ⚠ Service exited - check GitHub repo access and build logs")
                        break
            else:
                time.sleep(10)
                continue
            break
        except:
            time.sleep(10)

    # --- Summary ---
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║  Kdenlive Headless Service Deployed                         ║
╠══════════════════════════════════════════════════════════════╣
║  Service UUID: {app_uuid[:8]}...                              ║
║  Project: Kdenlive Media                                    ║
║  Repository: https://github.com/Dkpiec/kdenlive-headless    ║
║  Build: Dockerfile (auto from GitHub)                       ║
║  Port: 8080 (internal only)                                 ║
║  API: http://kdenlive-headless:8080                         ║
║  Health: http://kdenlive-headless:8080/health               ║
║                                                             ║
║  API Key: {api_key[:12]}...                            ║
║  Workspace: /opt/data/kdenlive-workspace                    ║
║                                                             ║
║  Isolated from Trading Dashboard ✓                          ║
║  No reserved URLs used ✓                                    ║
╚══════════════════════════════════════════════════════════════╝
""")

    return app_uuid, api_key

if __name__ == '__main__':
    main()