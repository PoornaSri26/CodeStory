from pathlib import Path

import pytest

from lib.plot import build_brag_plot
from lib.repo import LocalRepoFetcher
from lib.synthesis import render_audio_for
from workers.worker import set_status


def test_local_repo_fetch():
    lf = LocalRepoFetcher()
    info = lf.fetch("../..")  # workspace root has README.md
    assert info.readme, "README found"
    assert info.name, "name parsed"


def test_audio_written():
    lf = LocalRepoFetcher()
    info = lf.fetch("../..")
    plot = build_brag_plot(info, max_frames=2)
    audio_dir = Path("video-output/test-audio")
    audio_dir.mkdir(parents=True, exist_ok=True)
    for seg in plot.segments:
        seg.audio = str(render_audio_for(seg, audio_dir))
    assert all(Path(s.audio).exists() for s in plot.segments)
    import shutil

    shutil.rmtree(audio_dir, ignore_errors=True)


def test_set_status_transitions():
    job = {"job_id": "1", "status": "queued", "progress": 0.0}
    set_status(job, "scripting", "rendered script")
    assert job["status"] == "scripting"
    assert job["message"] == "rendered script"
    assert 0.0 <= job["progress"] <= 1.0
