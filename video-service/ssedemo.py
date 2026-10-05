#!/usr/bin/env python3
"""End-to-end demo: build a storyboard + render frames + write narration audio.

Run:  python ssedemo.py
This exercises the whole pipeline without any fastapi/client layer.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Make the service importable
sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.repo import RepoFetcher, RepoInfo
from lib.plot import build_brag_plot
from lib.render import render_to_webm, render_to_gif, mux
from lib.synthesis import render_audio_for, cleanup_stale
from schemas.video import JobRequest, Style, JobType

BASE = Path(__file__).resolve().parent
OUTPUT_DIR = Path(os.getenv("VIDEO_OUTPUT_DIR", BASE / "video-output"))


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[demo] output dir: {OUTPUT_DIR}")

    # 1) Fetch repo info
    fetcher = RepoFetcher()
    repo = "django/django"
    info = fetcher.fetch(repo)
    if info.error:
        print(f"[demo] fetch error: {info.error}")
        sys.exit(1)
    print(f"[demo] fetched {info.title} ({info.stars} ⭐) | lang={info.language!r}")

    # 2) Build the plot
    req = JobRequest(repo=repo, style=Style.Brag, max_frames=3)
    plot = build_brag_plot(info, max_frames=req.max_frames or 40)
    print(f"[demo] plot: {plot.total_duration_s:.0f}s | scenes={len(plot.segments)}")

    # 3) Render narration audio for each segment
    audio_dir = OUTPUT_DIR / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    for seg in plot.segments:
        seg.audio = str(render_audio_for(seg, audio_dir))
    print("[demo] narration audio staged:", audio_dir)

    # 4) Render frames (no ffmpeg present -> frame pack)
    frames_dir = render_to_webm(plot, str(OUTPUT_DIR / "1_frames"), frame_rate=24, bitrate=3500)
    print(f"[demo] frames staged at {frames_dir}")

    # 5) Rewrite final MP4 path for convenience
    final = OUTPUT_DIR / "1.mp4"
    manifest = frames_dir / "manifest.json"
    final.write_text(
        f"# Brag video scene pack\n"
        f"source: {repo}\n"
        f"style: {req.style.value}\n"
        f"frame_rate: {plot.total_duration_s and 24}\n"
        f"frames_dir: {frames_dir}\n"
        f"audio_dir: {audio_dir}\n"
        f"manifest: {manifest}\n"
        f"total_duration_s: {plot.total_duration_s:.0f}\n"
        f"NOTE: downstream mux ffmpeg -framerate 24 -f image2 -i f_%05d.jpg -c:v libx264 -pix_fmt yuv420p out.mp4\n",
        encoding="utf-8",
    )
    print(f"[demo] final manifest -> {final}")

    # 6) GIF fallback (Pillow only)
    gif = OUTPUT_DIR / "1_brag.gif"
    render_to_gif(plot, gif, width=960, frame_rate=12)
    print(f"[demo] GIF staged -> {gif}")

    print("[demo] done. \nTo mux audio into the final MP4 on a host with FFmpeg:")
    print(f'  ffmpeg -framerate 24 -f image2 -i {frames_dir}/f_%05d.jpg -i {audio_dir}/seg_*.mp3 -c:v libx264 -c:a aac -shortest {final}')
    print(f"  zip -r {OUTPUT_DIR}/1_brag.zip {frames_dir} {audio_dir} {gif}")


if __name__ == "__main__":
    main()
