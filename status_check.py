#!/usr/bin/env python3
"""
Kdenlive Headless - Status and version information
Quick diagnostic utility for verifying container setup
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path
from shutil import which


def get_versions():
    """Check installed tool versions"""
    versions = {}
    for tool in ['melt', 'ffmpeg', 'python3', 'kdenlive', 'curl']:
        path = which(tool)
        if path:
            import subprocess
            try:
                result = subprocess.run([path, '--version'], capture_output=True, text=True, timeout=5)
                first_line = result.stdout.split('\n')[0] if result.stdout else "version unknown"
                versions[tool] = first_line.strip()
            except Exception:
                versions[tool] = f"found at {path}"
        else:
            versions[tool] = "NOT FOUND"
    return versions


def get_container_info():
    """Get container environment info"""
    info = {
        "timestamp": datetime.utcnow().isoformat(),
        "workspace": {
            "path": "/workspace",
            "exists": Path("/workspace").exists(),
            "writable": os.access("/workspace", os.W_OK),
        },
        "projects_dir": {
            "path": "/workspace/projects",
            "exists": Path("/workspace/projects").exists(),
        },
        "results_dir": {
            "path": "/workspace/results",
            "exists": Path("/workspace/results").exists(),
        },
        "render_engine": {
            "melt_available": which("melt") is not None,
            "ffmpeg_available": which("ffmpeg") is not None,
        },
        "api": {
            "port": 8080,
            "api_key_set": bool(os.environ.get("KDENLIVE_API_KEY")),
        },
        "versions": get_versions(),
    }
    return info


def main():
    info = get_container_info()
    print(json.dumps(info, indent=2))

    # Check for critical issues
    issues = []
    if not info["render_engine"]["melt_available"]:
        issues.append("CRITICAL: melt not found - cannot render")
    if not info["render_engine"]["ffmpeg_available"]:
        issues.append("WARNING: ffmpeg not found")
    if not info["workspace"]["writable"]:
        issues.append("CRITICAL: /workspace not writable")
    if not info["api"]["api_key_set"]:
        issues.append("WARNING: No API key set")

    if issues:
        print("\nISSUES:")
        for issue in issues:
            print(f"  - {issue}")
        sys.exit(1)
    else:
        print("\nAll checks passed")
        sys.exit(0)


if __name__ == "__main__":
    main()