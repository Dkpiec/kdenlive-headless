#!/usr/bin/env python3
"""
Kdenlive Headless Render API
FastAPI application for Hermes integration
Runs inside the Kdenlive container on port 8080
"""

import os
import sys
import json
import uuid
import time
import subprocess
import shutil
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any
from concurrent.futures import ThreadPoolExecutor

from fastapi import FastAPI, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('/workspace/config/api.log')
    ]
)
logger = logging.getLogger("kdenlive_api")

app = FastAPI(
    title="Kdenlive Headless Render API",
    description="API for headless video rendering via Kdenlive/MLT",
    version="1.0.0"
)

# CORS for internal container communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Internal network only
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
API_KEY = os.environ.get("KDENLIVE_API_KEY", "CHANGE_ME_TO_SECURE_RANDOM_KEY")
WORKSPACE_PATH = Path(os.environ.get("WORKSPACE_PATH", "/workspace"))
PROJECTS_DIR = WORKSPACE_PATH / "projects"
RESULTS_DIR = WORKSPACE_PATH / "results"
CONFIG_DIR = WORKSPACE_PATH / "config"
MAX_CONCURRENT_RENDERS = int(os.environ.get("MAX_CONCURRENT_RENDERS", "2"))

# Ensure directories exist
PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)
CONFIG_DIR.mkdir(parents=True, exist_ok=True)

# Thread pool for background renders
render_executor = ThreadPoolExecutor(max_workers=MAX_CONCURRENT_RENDERS)

# Job tracking
jobs: Dict[str, Dict[str, Any]] = {}

# Verify key dependencies are available
RENDER_AVAILABLE = shutil.which("melt") is not None

logger.info(f"API initialized: render_available={RENDER_AVAILABLE}, workspace={WORKSPACE_PATH}")


# --- Data Models ---

class RenderJobRequest(BaseModel):
    project_path: str = Field(...,..., min_length=1)
    output_name: str = Field(..., min_length=1)
    fps: int = Field(30, ge=1, le=120)
    resolution: str = Field("1920x1080", min_length=1)
    quality: str = Field("medium", pattern="^(low|medium|high|lossless)$")
    api_key: str = Field(...)


class RenderJobResponse(BaseModel):
    job_id: str
    status: str
    project_path: str
    output_path: str
    fps: int
    resolution: str
    quality: str
    submitted_at: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    progress: int
    start_time: Optional[str]
    end_time: Optional[str]
    output_path: Optional[str]
    error: Optional[str]
    log: Optional[str]


class HealthResponse(BaseModel):
    status: str
    version: str
    render_available: bool
    jobs_active: int
    jobs_completed: int
    workspace_exists: bool
    workspace_writable: bool
    projects_dir_exists: bool
    results_dir_exists: bool


# --- API Endpoints ---

@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Check container and API health"""
    return {
        "status": "healthy",
        "version": "1.0.0",
        "render_available": RENDER_AVAILABLE,
        "jobs_active": sum(1 for j in jobs.values() if j["status"] == "running"),
        "jobs_completed": sum(1 for j in jobs.values() if j["status"] in ("completed", "failed")),
        "workspace_exists": WORKSPACE_PATH.exists(),
        "workspace_writable": os.access(WORKSPACE_PATH, os.W_OK),
        "projects_dir_exists": PROJECTS_DIR.exists(),
        "results_dir_exists": RESULTS_DIR.exists(),
    }


@app.post("/submit_render_job", response_model=RenderJobResponse)
async def submit_render_job(request: RenderJobRequest, background_tasks: BackgroundTasks):
    """Submit a video render job"""
    # Authenticate
    if request.api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    # Validate melt is available
    if not RENDER_AVAILABLE:
        raise HTTPException(status_code=503, detail="Render engine (melt) not available")

    # Resolve and validate project path
    project_path = _resolve_project_path(request.project_path)
    if not project_path.exists():
        raise HTTPException(status_code=404, detail=f"Project not found: {request.project_path}")

    # Validate project format
    if not _validate_project(project_path):
        raise HTTPException(status_code=400, detail=f"Invalid project format: {request.project_path}")

    # Build output path
    output_name = request.output_name if request.output_name.endswith(('.mp4', '.mov', '.mkv', '.avi')) else f"{request.output_name}.mp4"
    output_path = RESULTS_DIR / output_name

    # Generate job ID
    job_id = str(uuid.uuid4())

    # Store job info
    jobs[job_id] = {
        "status": "queued",
        "progress": 0,
        "start_time": None,
        "end_time": None,
        "project_path": str(project_path),
        "output_path": str(output_path),
        "fps": request.fps,
        "resolution": request.resolution,
        "quality": request.quality,
        "error": None,
        "log": "",
        "submitted_at": datetime.utcnow().isoformat(),
    }

    # Submit background job
    background_tasks.add_task(_run_render_job, job_id)

    logger.info(f"Render job submitted: {job_id} -> {output_name}")

    return RenderJobResponse(
        job_id=job_id,
        status="queued",
        project_path=str(project_path),
        output_path=str(output_path),
        fps=request.fps,
        resolution=request.resolution,
        quality=request.quality,
        submitted_at=jobs[job_id]["submitted_at"],
    )


@app.get("/job_status/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str, api_key: str = None):
    """Check status of a render job"""
    if api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    job = jobs[job_id]

    return JobStatusResponse(
        job_id=job_id,
        status=job["status"],
        progress=job["progress"],
        start_time=job["start_time"],
        end_time=job["end_time"],
        output_path=job.get("output_path"),
        error=job.get("error"),
        log=job.get("log", ""),
    )


@app.get("/jobs", response_model=list)
async def list_jobs(api_key: str = None):
    """List all render jobs"""
    if api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return [{"job_id": k, **v} for k, v in jobs.items()]


@app.get("/workspace/list")
async def list_workspace(api_key: str = None, directory: str = None):
    """List files in workspace"""
    if api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    target_dir = WORKSPACE_PATH
    if directory:
        target_dir = WORKSPACE_PATH / directory
        if not str(target_dir).startswith(str(WORKSPACE_PATH)):
            raise HTTPException(status_code=400, detail="Directory must be within workspace")

    if not target_dir.exists():
        raise HTTPException(status_code=404, detail=f"Directory not found: {directory}")

    result = {"path": str(target_dir), "files": []}
    for item in sorted(target_dir.iterdir()):
        result["files"].append({
            "name": item.name,
            "path": str(item),
            "is_dir": item.is_dir(),
            "size": item.stat().st_size if item.is_file() else 0,
            "modified": item.stat().st_mtime,
        })

    return result


@app.post("/render/xmpeg", response_model=dict)
async def render_xmpeg(request: RenderJobRequest, background_tasks: BackgroundTasks):
    """
    Legacy endpoint: Submit render using xmpeg-compatible parameters.
    Returns a render job ID for status checking.
    """
    return await submit_render_job(request, background_tasks)


# --- Internal Functions ---

def _resolve_project_path(user_path: str) -> Path:
    """Resolve project path, handling absolute/relative paths"""
    path = Path(user_path)
    if path.is_absolute():
        # Only allow paths within workspace
        if str(path).startswith(str(WORKSPACE_PATH)):
            return path
        raise HTTPException(status_code=400, detail="Project must be within workspace")
    # Relative to projects directory
    return PROJECTS_DIR / path


def _validate_project(project_path: Path) -> bool:
    """Validate that project file is a valid XML/Kdenlive project"""
    try:
        content = project_path.read_text(encoding='utf-8', errors='ignore')
        # Check for MLT/Kdenlive XML markers
        return '<mlt' in content or '<kdenlive' in content or '<document' in content
    except Exception:
        return False


def _build_melt_command(project_path: Path, output_path: Path, fps: int, resolution: str, quality: str) -> list:
    """Build the melt command for rendering"""
    cmd = ["melt", str(project_path)]

    # Consumer settings based on quality
    quality_presets = {
        "low": "vcodec=libx264,crf=28,acodec=aac,ab=128k",
        "medium": "vcodec=libx264,crf=23,acodec=aac,ab=192k",
        "high": "vcodec=libx264,crf=18,acodec=aac,ab=256k",
        "lossless": "vcodec=ffv1,acodec=pcm_s16le",
    }

    codec_params = quality_presets.get(quality, quality_presets["medium"])

    cmd.append(f"-consumer avformat:{output_path}")
    cmd.append(codec_params)
    cmd.append(f"frame_rate={fps}")

    # Resolution
    if 'x' in resolution:
        width, height = resolution.split('x', 1)
        cmd.append(f"width={width}")
        cmd.append(f"height={height}")
    else:
        cmd.append(f"width={resolution}")

    # Performance
    cmd.append("threads=0")
    cmd.append("pix_fmt=yuv420p")

    return cmd


def _run_render_job(job_id: str):
    """Execute a render job in the background"""
    job = jobs[job_id]
    if not job:
        return

    try:
        # Update status
        job["status"] = "running"
        job["start_time"] = datetime.utcnow().isoformat()
        logger.info(f"Starting render job: {job_id}")

        project_path = Path(job["project_path"])
        output_path = Path(job["output_path"])
        fps = job["fps"]
        resolution = job["resolution"]
        quality = job["quality"]

        # Build and log command (sanitize for logging)
        cmd = _build_melt_command(project_path, output_path, fps, resolution, quality)
        logger.info(f"Render command: {' '.join(cmd[:5])} ...")

        # Execute melt
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=str(WORKSPACE_PATH),
            env={**os.environ, "HOME": str(Path.home())},
        )

        # Monitor progress
        import time as _time
        start = _time.time()
        while process.poll() is None:
            _time.sleep(5)
            elapsed = _time.time() - start
            estimated_duration = 300  # Default 5 min estimate
            progress = min(int((elapsed / estimated_duration) * 100), 95)
            job["progress"] = progress

            # Read any output
            stdout_line = process.stdout.readline() if process.stdout else ""
            if stdout_line:
                job["log"] += stdout_line

        # Get remaining output
        stdout, stderr = process.communicate()
        job["log"] += stdout + stderr

        if process.returncode == 0:
            job["status"] = "completed"
            job["progress"] = 100
            job["end_time"] = datetime.utcnow().isoformat()
            logger.info(f"Render completed: {job_id}")
        else:
            job["status"] = "failed"
            job["error"] = f"Melt exited with code {process.returncode}"
            job["end_time"] = datetime.utcnow().isoformat()
            logger.error(f"Render failed: {job_id}: {stderr}")

    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)
        job["end_time"] = datetime.utcnow().isoformat()
        logger.error(f"Render error: {job_id}: {e}", exc_info=True)


@app.on_event("startup")
async def startup():
    logger.info("Kdenlive Headless Render API started")
    if not RENDER_AVAILABLE:
        logger.warning("melt not found in PATH - render jobs will fail")