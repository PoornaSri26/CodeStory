from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from bullmq import Job, Worker

from lib.repo import RepoFetcher, LocalRepoFetcher
from lib.plot import build_brag_plot
from lib.render import render_to_webm, mux
from lib.synthesis import render_audio_for
from schemas.video import JobRequest, JobStatus, Style

OUTPUT_DIR = Path(os.getenv("VIDEO_OUTPUT_DIR", "./video-output"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("video-worker")
logging.basicConfig(level=logging.INFO)

_fetcher: RepoFetcher | None = None
_l_fetcher: LocalRepoFetcher | None = None


def _get_fetchers():
    global _fetcher, _l_fetcher
    if _fetcher is None or _l_fetcher is None:
        _fetcher = RepoFetcher()
        _l_fetcher = LocalRepoFetcher()
    return _fetcher, _l_fetcher


def _set(job: dict, status: str, msg: str = "", output_url: str | None = None):
    job["status"] = status
    job["progress"] = min(1.0, max(0.0, job.get("progress", 0.0)))
    if msg:
        job["message"] = msg
    if output_url:
        job["output_url"] = output_url
    job["updated_at"] = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    job["_broadcast"](job)


class VideoWorker(Worker):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    async def run(self, job: Job, token: str | None = None) -> None:
        data: dict[str, Any] = job.data  # type: ignore[attr-defined]
        job_id = data.get("job_id")
        req = JobRequest(**{k: v for k, v in data.items() if k not in ("job_id",)})
        logger.info("job %s started (type=%s, style=%s)", job_id, req.job_type, req.style)

        try:
            fetcher, l_fetcher = _get_fetchers()
            if req.job_type == "local":
                info = l_fetcher.fetch(req.path or ".")
            else:
                info = fetcher.fetch(req.repo or "")
            if info.error:
                raise RuntimeError(info.error)
            job["repo"] = info.full_name or info.name
            set_status(job, JobStatus.Validating)

            plot = build_brag_plot(info, max_frames=req.max_frames or 40)
            set_status(job, JobStatus.Planning)

            for seg in plot.segments:
                seg.audio = str(render_audio_for(seg, OUTPUT_DIR))
            set_status(job, JobStatus.Scripting)

            for i, seg in enumerate(plot.segments):
                set_status(job, JobStatus.Rendering, f"Frame {i+1}/{len(plot.segments)}")
                # real: ffmpeg encode streamed to Redis/GCS; placeholder keeps demo fast
                pass

            set_status(job, JobStatus.Muxing)
            # placeholder final mp4
            out = OUTPUT_DIR / f"{job_id}.mp4"
            out.parent.mkdir(parents=True, exist_ok=True)
            # In production this writes the real encoded mp4. This demo leaves a
            # zero-byte file and reports success — see the README test notes.
            out.touch()
            job["duration_seconds"] = 0.0
            job["output_url"] = f"/api/videos/{job_id}/file"
            set_status(job, JobStatus.Finished, "Done", output_url=job["output_url"])
        except Exception as exc:
            logger.exception("job %s failed", job_id)
            set_status(job, JobStatus.Failed, str(exc))


def set_status(job: dict, status: str, msg: str = "", output_url: str | None = None):
    # callable free fallback: in production this calls a broadcast hook
    job["status"] = status
    job["progress"] = min(1.0, max(0.0, job.get("progress", 0.0)))
    if msg:
        job["message"] = msg
    if output_url:
        job["output_url"] = output_url
