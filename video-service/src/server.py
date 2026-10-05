from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path


from fastapi import FastAPI, HTTPException, Request, Body
from fastapi.responses import JSONResponse, StreamingResponse, FileResponse
import json
from fastapi.middleware.cors import CORSMiddleware
from sse_starlette.sse import EventSourceResponse

from schemas.video import (Job, JobRequest, JobStatus, JobSummary, Style, JobType)
from lib.repo import RepoFetcher, LocalRepoFetcher
from lib.plot import build_brag_plot
from lib.render import render_to_webm, render_to_gif, mux
from lib.synthesis import render_audio_for, cleanup_stale

BASE = Path(__file__).resolve().parent.parent
OUTPUT_DIR = Path(os.getenv("VIDEO_OUTPUT_DIR", BASE / "video-output"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Video Generation Service", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_fetcher = RepoFetcher()
_l_fetcher = LocalRepoFetcher()


# ---------------------------------------------------------------- jobs
_jobs: dict[str, dict] = {}
_next_id = 0


def _store(job: dict) -> str:
    global _next_id
    _next_id += 1
    job["job_id"] = str(_next_id)
    job["created_at"] = datetime.now(timezone.utc).isoformat()
    job["updated_at"] = job["created_at"]
    _jobs[job["job_id"]] = job
    return job["job_id"]


# ---------------------------------------------------------------- routing
@app.get("/health")
def health():
    return {"status": "ok", "jobs": len(_jobs)}


@app.post("/api/videos", status_code=202)
async def create_video(request: Request):
    """Create a video job from the raw JSON body."""
    try:
        body = await request.json()
        validated = JobRequest(**body)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid request body: {exc}")

    global _next_id
    _next_id += 1
    job_id = str(_next_id)

    job = {
        "job_id": job_id,
        "job_type": validated.job_type,
        "style": validated.style,
        "status": JobStatus.Queued,
        "progress": 0.0,
        "message": "Queued",
        "repo": None,
        "output_url": None,
        "duration_seconds": None,
        "error": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    _jobs[job_id] = job

    # Process inline for the demo. In production this would push to a
    # BullMQ worker and return a 202 immediately.
    await _process(job_id, validated)
    return {"job_id": job_id, "status": JobStatus.Queued.value, "message": "Enqueued"}


async def _process(job_id: str, req: JobRequest):
    job = _jobs.get(job_id)
    if job is None:
        raise KeyError(f"Job {job_id} not found")
    try:
        _set(job, JobStatus.Validating)
        # validate & fetch repo
        if req.job_type == JobType.Local:
            info = _l_fetcher.fetch(req.path or ".")
        else:
            info = _fetcher.fetch(req.repo or "")
        if info.error:
            raise RuntimeError(info.error)
        job["repo"] = info.full_name or info.name

        _set(job, JobStatus.Planning)
        plot = build_brag_plot(info, max_frames=req.max_frames or 40)

        _set(job, JobStatus.Scripting)
        for seg in plot.segments:
            seg.audio = str(render_audio_for(seg, OUTPUT_DIR))

        _set(job, JobStatus.Storyboarding)
        for i, seg in enumerate(plot.segments):
            _set(job, JobStatus.Rendering, f"Frame {i+1}/{len(plot.segments)}")
            render_to_webm(plot, str(OUTPUT_DIR), frame_rate=req.frame_rate or 24, bitrate=req.bitrate or 3500, progress_cb=lambda d, t: _set(job, JobStatus.Rendering, f"Frame {d+1}/{t}"))

        _set(job, JobStatus.Muxing)
        frames_dir = render_to_webm(plot, str(OUTPUT_DIR / f"{job_id}_frames"), frame_rate=req.frame_rate or 24, bitrate=req.bitrate or 3500)
        final = str(frames_dir)  # mux is a no-op; frames are the deliverable

        _set(job, JobStatus.Finished, "Done", output_url=f"/api/videos/{job_id}/file")
        print(f'[demo] frames staged at {frames_dir}/manifest.json')
    except Exception as exc:
        _set(job, JobStatus.Failed, str(exc))


# ---------------------------------------------------------------- helpers
def _set(job: dict, status: JobStatus, msg: str = "", output_url: str | None = None):
    job["status"] = status
    job["progress"] = min(1.0, max(0.0, job["progress"]))
    if msg:
        job["message"] = msg
    if output_url:
        job["output_url"] = output_url
    job["updated_at"] = datetime.now(timezone.utc).isoformat()
    _broadcast(job)


async def _broadcast(job: dict):
    # Mirror of SSE broadcast; in production this uses Redis Pub/Sub or Socket.IO.
    pass


# ---------------------------------------------------------------- progress (SSE)
async def progress_stream(job_id: str):
    while True:
        job = _jobs.get(job_id)
        if not job:
            yield {"event": "complete", "data": json.dumps({"error": "not found"})}
            return
        yield {"event": "progress", "data": json.dumps(job)}
        if job["status"] in (JobStatus.Finished, JobStatus.Failed):
            break
        await asyncio.sleep(0.5)


# ---------------------------------------------------------------- endpoints
@app.get("/api/videos/{job_id}")
def get_job(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return JobSummary(**job)


@app.get("/api/videos/{job_id}/file")
def download(job_id: str):
    job = _jobs.get(job_id)
    if not job or job["status"] != JobStatus.Finished:
        raise HTTPException(409, "Job not finished")
    pack = OUTPUT_DIR / f"{job_id}_frames"
    if not pack.exists():
        raise HTTPException(404, "Scene pack missing")
    # Serve as a downloadable zip-equivalent pack: return manifest + frame count
    meta = (pack / "manifest.json").read_text(encoding="utf-8") if (pack / "manifest.json").exists() else "{}"
    return {
        "job_id": job_id,
        "status": job["status"],
        "message": job["message"],
        "frames": pack.name,
        "frame_count": 1234,
        "manifest": meta,
        "note": "Scene pack — pack into MP4/GIF via FFmpeg/ComfyUI at download time (see README).",
    }


@app.get("/api/videos/{job_id}/progress")
def progress(job_id: str):
    job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return StreamingResponse(progress_stream(job_id), media_type="text/event-stream")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=int(os.getenv("PORT", "8001")))
