#!/usr/bin/env python3
"""
Test script to validate Kdenlive headless render setup
Run from Hermes container to test the API
"""

import os
import sys
import time
import requests
import json
from pathlib import Path

# Configuration
KDENLIVE_URL = os.environ.get("KDENLIVE_URL", "http://kdenlive-headless:8080")
API_KEY = os.environ.get("KDENLIVE_API_KEY", "CHANGE_ME_TO_SECURE_RANDOM_KEY")

def test_health():
    """Test health endpoint"""
    print("Testing health endpoint...")
    try:
        response = requests.get(f"{KDENLIVE_URL}/health", timeout=10)
        if response.status_code == 200:
            data = response.json()
            print(f"  ✓ Health: {data['status']}")
            print(f"  ✓ Render engine: {'available' if data['render_available'] else 'NOT AVAILABLE'}")
            print(f"  ✓ Workspace: {'writable' if data['workspace_writable'] else 'NOT WRITABLE'}")
            return True
        else:
            print(f"  ✗ Health check failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"  ✗ Health check error: {e}")
        return False


def create_sample_project():
    """Create a simple test project"""
    project_path = Path("/workspace/projects/test_project.mlt")
    project_content = '''<?xml version="1.0" encoding="UTF-8"?>
<mlt profile="av_profile_pal_25fps">
  <producer id="producer_0" in="0" out="0">
    <property name="resource">/workspace/projects/input.mp4</property>
    <property name="type">consumer</property>
  </producer>
  <playlist id="playlist_0">
    <entry producer="producer_0" in="0" out="0"/>
  </playlist>
  <tractor id="tractor_0">
    <track index="video" producer="playlist_0"/>
    <track index="audio" producer="playlist_0"/>
  </tractor>
  <consumer id="consumer_0">
    <property name="resource">/workspace/results/test_output.mp4</property>
    <property name="target_profile">av_profile_pal_25fps</property>
  </consumer>
</mlt>'''
    project_path.write_text(project_content)
    print(f"  Created test project: {project_path}")
    return str(project_path)


def test_submit_render():
    """Test submitting a render job"""
    print("\nTesting render job submission...")
    
    # Check if we have a test input file
    test_input = Path("/workspace/projects/input.mp4")
    if not test_input.exists():
        print(f"  ⚠ No test input at {test_input}, creating placeholder...")
        test_input.write_bytes(b"PLACEHOLDER - replace with real video")
    
    # Create sample project
    project_path = create_sample_project()
    
    try:
        response = requests.post(
            f"{KDENLIVE_URL}/submit_render_job",
            data={
                "project_path": project_path,
                "output_name": "test_output.mp4",
                "fps": 30,
                "resolution": "1280x720",
                "quality": "low",
                "api_key": API_KEY,
            },
            timeout=15
        )
        if response.status_code == 200:
            data = response.json()
            print(f"  ✓ Job submitted: {data['job_id']}")
            return data['job_id']
        else:
            print(f"  ✗ Submit failed: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"  ✗ Submit error: {e}")
        return None


def test_job_status(job_id):
    """Poll job status"""
    print(f"\nPolling job status: {job_id}")
    for i in range(60):  # Up to 5 minutes
        try:
            response = requests.get(
                f"{KDENLIVE_URL}/job_status/{job_id}",
                params={"api_key": API_KEY},
                timeout=10
            )
            if response.status_code == 200:
                data = response.json()
                status = data['status']
                progress = data['progress']
                print(f"  [{i*5}s] Status: {status}, Progress: {progress}%")
                
                if status == "completed":
                    print(f"  ✓ Render completed: {data.get('output_path')}")
                    return True
                elif status in ("failed", "error"):
                    print(f"  ✗ Render failed: {data.get('error')}")
                    if data.get('log'):
                        print(f"  Log: {data['log'][:500]}")
                    return False
            else:
                print(f"  ✗ Status check failed: {response.status_code}")
        except Exception as e:
            print(f"  ✗ Status error: {e}")
        
        time.sleep(5)
    
    print("  ⚠ Timeout waiting for job completion")
    return False


def test_workspace_list():
    """Test workspace listing"""
    print("\nTesting workspace list...")
    try:
        response = requests.get(
            f"{KDENLIVE_URL}/workspace/list",
            params={"api_key": API_KEY},
            timeout=10
        )
        if response.status_code == 200:
            data = response.json()
            print(f"  ✓ Projects: {len(data.get('projects', []))}")
            print(f"  ✓ Results: {len(data.get('results', []))}")
            for p in data.get('projects', []):
                print(f"    - {p['name']} ({p['size']} bytes)")
            for r in data.get('results', []):
                print(f"    - {r['name']} ({r['size']} bytes)")
            return True
        else:
            print(f"  ✗ List failed: {response.status_code}")
            return False
    except Exception as e:
        print(f"  ✗ List error: {e}")
        return False


def main():
    print("=" * 60)
    print("Kdenlive Headless Render API - Integration Test")
    print("=" * 60)
    print(f"Target: {KDENLIVE_URL}")
    print(f"API Key: {'SET' if API_KEY != 'CHANGE_ME_TO_SECURE_RANDOM_KEY' else 'NOT SET (using default)'}")
    
    # Test health
    if not test_health():
        print("\n✗ Health check failed - aborting")
        sys.exit(1)
    
    # Test workspace list
    test_workspace_list()
    
    # Test render job
    job_id = test_submit_render()
    if job_id:
        test_job_status(job_id)
    
    print("\n" + "=" * 60)
    print("Test complete")
    print("=" * 60)


if __name__ == "__main__":
    main()