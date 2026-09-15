#!/bin/bash
set -e

# Copy this entrypoint script into the image
# Use this entrypoint for the kdenlive headless container

cat > /app/entrypoint.sh <<'EOF'
#!/bin/bash

# Start SSH daemon in background for secure connections
/usr/sbin/sshd -D &
SSH_PID=$!

# Wait for SSH to be ready
for i in {1..30}; do
    if sshd -t 2>/dev/null; then
        echo "SSH daemon initialized successfully"
        break
    fi
    sleep 1
done

# Function to validate Kdenlive project file
validate_project_file() {
    local project_file=$1
    if [[ ! -f "$project_file" ]]; then
        echo "Error: Project file not found: $project_file"
        return 1
    fi
    
    # Check if it's a valid XML file
    if ! grep -q "^<mlt profile" "$project_file" 2>/dev/null; then
        echo "Error: Invalid Kdenlive project format"
        return 1
    fi
    
    return 0
}

# Function to check workspace directories
check_workspace() {
    local project_dir=$1
    local result_dir=$2
    
    if [[ ! -d "$project_dir" ]]; then
        mkdir -p "$project_dir"
    fi
    
    if [[ ! -d "$result_dir" ]]; then
        mkdir -p "$result_dir"
    fi
    
    # Check if render user has access to workspace
    if ! su -s /bin/bash render -c "ls $project_dir" 2>/dev/null; then
        echo "Error: Render user cannot access workspace directory"
        return 1
    fi
    
    return 0
}

# Function to execute melt render command
execute_melt_render() {
    local project_file=$1
    local output_file=$2
    local fps=$3
    local resolution=$4
    
    echo "Starting render: $project_file -> $output_file (fps: $fps, resolution: $resolution)"
    
    # Create render command
    local melt_cmd="melt '$project_file' -consumer avformat:'$output_file' \"
    melt_cmd+="vcodec=libx264,profile=main,vframes=0 \"
    melt_cmd+="acodec=aac,ac=2,ar=48000,ab=192 \"
    melt_cmd+="threads=0 \"
    melt_cmd+="pix_fmt=yuv420p \"
    melt_cmd+="set.tsync,fps=$fps \"
    melt_cmd+"set.resolution,$resolution \"
    melt_cmd+"set.sws=5"
    
    # Execute as render user with output to log
    su -s /bin/bash render -c "cd /workspace && $melt_cmd" \
        "&> /workspace/render.log" \
        || {
            echo "Render failed. Check log at /workspace/render.log"
            cat /workspace/render.log 2>/dev/null | tail -50
            return 1
        }
    
    return 0
}

# Simple API server using Python
python3 - <<'PYEOF'
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseSettings
from typing import Optional
import subprocess
import os
import json
import uuid
import time
import signal
from pathlib import Path

app = FastAPI(title="Kdenlive Headless Render API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost", "http://127.0.0.1"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class Settings(BaseSettings):
    api_key: str = "KDENLIVE_API_KEY_2024_SECURE"
    workspace_path: str = "/workspace"
    max_concurrent_renders: int = 2

settings = Settings()

# In-memory job tracking (use Redis/database in production)
active_jobs = {}

@app.get("/")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "active_jobs": len(active_jobs),
        "workspace_path": settings.workspace_path
    }

@app.post("/submit_render_job")
async def submit_render_job(
    background_tasks: BackgroundTasks,
    project_path: str,
    output_name: str,
    fps: int = 30,
    resolution: str = "1920x1080",
    api_key: str = None
):
    # Validate API key
    if api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    # Validate workspace
    workspace_path = Path(settings.workspace_path)
    project_path = Path(project_path)
    output_path = workspace_path / "results" / output_name
    
    # Check if project file exists
    if not project_path.exists():
        raise HTTPException(status_code=400, detail=f"Project file not found: {project_path}")
    
    # Check for valid project format
    try:
        with open(project_path, 'r') as f:
            content = f.read()
            if '<mlt profile' not in content:
                raise HTTPException(status_code=400, detail="Invalid Kdenlive project file format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading project file: {str(e)}")
    
    # Check workspace permissions
    if not os.access(workspace_path / "projects", os.W_OK):
        raise HTTPException(status_code=403, detail="No write permission to workspace/projects")
    
    if not os.access(workspace_path / "results", os.W_OK):
        raise HTTPException(status_code=403, detail="No write permission to workspace/results")
    
    # Generate unique job ID
    job_id = str(uuid.uuid4())
    
    # Submit background render job
    def render_job():
        try:
            active_jobs[job_id] = {"status": "running", "progress": 0, "start_time": time.time()}
            
            # Execute melt command
            melt_cmd = f"melt '{project_path}' -consumer avformat:'{output_path}' vcodec=libx264,profile=main,vframes=0 acodec=aac,ac=2,ar=48000,ab=192 threads=0 pix_fmt=yuv420p set.tsync,fps={fps} set.resolution,{resolution} set.sws=5"
            
            process = subprocess.Popen(
                melt_cmd,
                shell=True,
                cwd="/workspace",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                preexec_fn=os.setsid,
                env={**os.environ, "HOME": "/home/render"}
            )
            
            stdout, stderr = process.communicate()
            
            if process.returncode == 0:
                active_jobs[job_id] = {
                    "status": "completed",
                    "progress": 100,
                    "start_time": active_jobs[job_id]["start_time"],
                    "end_time": time.time(),
                    "output_path": str(output_path),
                    "log": stdout.decode() + stderr.decode()
                }
            else:
                active_jobs[job_id] = {
                    "status": "failed",
                    "progress": 0,
                    "start_time": active_jobs[job_id]["start_time"],
                    "error": f"Render failed with exit code {process.returncode}",
                    "log": stdout.decode() + stderr.decode() + stderr.decode()
                }
        except Exception as e:
            active_jobs[job_id] = {
                "status": "error",
                "progress": 0,
                "error": str(e),
                "start_time": active_jobs[job_id]["start_time"] if job_id in active_jobs else time.time()
            }
    
    background_tasks.add_task(render_job)
    
    return {
        "job_id": job_id,
        "status": "submitted",
        "project_path": str(project_path),
        "output_path": str(output_path),
        "expected_fps": fps,
        "expected_resolution": resolution
    }

@app.get("/job_status/{job_id}")
async def get_job_status(job_id: str, api_key: str = None):
    # Validate API key
    if api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    if job_id not in active_jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    
    job_status = active_jobs[job_id].copy()
    
    # Calculate progress if running
    if job_status["status"] == "running":
        start_time = job_status.get("start_time", time.time())
        elapsed = time.time() - start_time
        job_status["progress"] = min(int((elapsed / 300) * 100), 95)  # Max 5 min estimated render time
    
    return job_status

@app.get("/workspace/list")
async def list_workspace(api_key: str = None):
    if api_key != settings.api_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    
    workspace = Path(settings.workspace_path)
    projects = []
    results = []
    
    if workspace.exists():
        for project_file in workspace.glob("projects/*.kdenlive"):
            projects.append({
                "name": project_file.name,
                "path": str(project_file),
                "size": project_file.stat().st_size,
                "modified": project_file.stat().st_mtime
            })
        
        for result_file in workspace.glob("results/*.mp4"):
            results.append({
                "name": result_file.name,
                "path": str(result_file),
                "size": result_file.stat().st_size,
                "modified": result_file.stat().st_mtime
            })
    
    return {
        "projects": projects,
        "results": results,
        "total_projects": len(projects),
        "total_results": len(results)
    }

@app.get("/health")
async def detailed_health_check():
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "workspace_path": settings.workspace_path,
        "active_jobs": len(active_jobs),
        "environment": {
            "python_version": f"{os.sys.version_info.major}.{os.sys.version_info.minor}.{os.sys.version_info.micro}",
            "workspace_exists": os.path.exists(settings.workspace_path),
            "workspace_writable": os.access(settings.workspace_path, os.W_OK)
        }
    }

if __name__ == "__main__":
    import uvicorn
    print("Starting Kdenlive Headless Render API on port 8080")
    uvicorn.run(app, host="0.0.0.0", port=8080, access_log=False)
PYEOF

# Start the API server
exec /usr/bin/python3 -m pip install --no-cache-dir fastapi uvicorn python-multipart fastapi-mcp orjson psutil fastapi-cors 2>/dev/null || true
exec python3 -m pip install --no-cache-dir fastapi uvicorn python-multipart fastapi-mcp orjson psutil fastapi-cors 2>/dev/null || true

cd /app
python3 -m uvicorn kdenlive_api:app --host 0.0.0.0 --port 8080

# Wait for API to start
for i in {1..30}; do
    if curl -s http://localhost:8080/health >/dev/null 2>&1; then
        echo "Kdenlive Headless API started successfully"
        break
    fi
    sleep 2
done

# Keep container running
while true; do
    sleep 60
    # Check if SSH is still running
    if ! pgrep -f "sshd" >/dev/null; then
        echo "SSH daemon stopped, restarting"
        /usr/sbin/sshd
    fi
    # Log status periodically
    echo "Kdenlive headless container running - $(date)" >> /var/log/kdenlive_container.log
    # Cleanup old jobs
    if [ -f "/app/kdenlive_api.py" ]; then
        python3 -c "
import json
import os
from pathlib import Path
api_path = Path('/app/kdenlive_api.py')
if api_path.exists():
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location('kdenlive_api', '/app/kdenlive_api.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        print('Module loaded: len(active_jobs) =', len(getattr(module, 'active_jobs', {})))
    except Exception as e:
        print('Module load error:', e)
else:
    print('API file not found')
" 2>/dev/null || true
    done
EOF