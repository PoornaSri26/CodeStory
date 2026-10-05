from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field, ConfigDict


class Style(str, Enum):
    """Narrative style for the generated brag video."""

    Brag = "brag"
    """Win centerpiece + narrated walkthrough + CTA. ≥30s, first-person brand voice."""

    Kando = "kando"
    """Montage of PRs, screenshots, and activity — no narration. Status-report style, auto-trimmed to ≤60s."""

    Lore = "lore"
    """Feature-first storyboard + narration. ~90s."""


class JobType(str, Enum):
    Repo = "repo"
    Local = "local"


class JobRequest(BaseModel):
    """Incoming video-generation request."""

    model_config = ConfigDict(extra="forbid")

    repo: str | None = Field(default=None, description="GitHub repo slug (org/repo) or full https URL")
    path: str | None = Field(default=None, description="Local source directory (when job_type=local)")
    job_type: JobType = Field(default=JobType.Repo, description="Repo or local path")
    style: Style = Field(default=Style.Brag, description="Narrative style preset")
    max_minutes: float | None = Field(
        default=None, ge=0.5, le=30, description="Hard cap on rendered video length in minutes"
    )
    max_frames: int | None = Field(
        default=None, ge=1, le=200, description="Max storyboard candidates from the LLM"
    )
    bitrate: int | None = Field(
        default=None, ge=500, le=20000, description="VBR target for the final MP4 (kbps)"
    )
    audio_kbps: int | None = Field(
        default=None, ge=48, le=640, description="MP3 narration bitrate (kbps)"
    )
    frame_rate: int | None = Field(
        default=None, ge=12, le=60, description="Output frame rate"
    )


class JobStatus(str, Enum):
    Queued = "queued"
    Validating = "validating"
    Planning = "planning"
    Scripting = "scripting"
    Storyboarding = "storyboarding"
    Rendering = "rendering"
    Muxing = "muxing"
    Finished = "finished"
    Failed = "failed"


class Job(BaseModel):
    job_id: str
    job_type: JobType
    style: Style
    status: JobStatus
    progress: float = 0.0
    message: str = ""
    repo: str | None = None
    output_url: str | None = None
    duration_seconds: float | None = None
    error: str | None = None
    created_at: str
    updated_at: str


class ProgressEvent(BaseModel):
    job_id: str
    progress: float
    stage: str
    message: str
    status: JobStatus
    output_url: str | None = None


class JobSummary(BaseModel):
    job_id: str
    repo: str | None
    style: Style
    status: JobStatus
    progress: float
    message: str
    duration_seconds: float | None
    output_url: str | None
    error: str | None
    created_at: str
    updated_at: str
