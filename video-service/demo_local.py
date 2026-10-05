#!/usr/bin/env python3
"""Local-repo end-to-end demo (no GitHub API needed).

Run:  python demo_local.py --repo ./my-project
"""
from __future__ import annotations
import argparse, os, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lib.repo import LocalRepoFetcher, RepoInfo
from lib.plot import build_brag_plot
from lib.render import render_to_webm, render_to_gif
from lib.synthesis import render_audio_for, cleanup_stale
from schemas.video import JobRequest, Style

BASE = Path(__file__).resolve().parent
OUTPUT_DIR = Path(os.getenv("VIDEO_OUTPUT_DIR", str(BASE / "video-output")))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", default=".", help="local repo path (default: current dir)")
    args = ap.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[local] output dir: {OUTPUT_DIR}")

    # 1) Fetch local info (no network)
    lf = LocalRepoFetcher()
    info = lf.fetch(args.repo)
    print(f"[local] fetched {info.title} | readme={len(info.readme)} chars | deps={len(info.package_json.get('dependencies', {}))}")

    # 2) Build plot
    req = JobRequest(job_type="local", path=str(Path(args.repo).resolve()),
                     style=Style.Brag, max_frames=8)
    plot = build_brag_plot(info, max_frames=req.max_frames or 8)
    print(f"[local] plot: {plot.total_duration_s:.0f}s | scenes={len(plot.segments)}")

    # 3) Narration audio
    audio_dir = OUTPUT_DIR / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    for seg in plot.segments:
        seg.audio = str(render_audio_for(seg, audio_dir))
    print(f"[local] narration staged at {audio_dir}")

    # 4) Frames (frame pack, since no ffmpeg)
    frames_dir = render_to_webm(plot, str(OUTPUT_DIR / "1_frames"), frame_rate=24, bitrate=3500)
    print(f"[local] frames staged at {frames_dir}")

    # 5) Deliverable manifest
    final = OUTPUT_DIR / "1.mp4"
    final.write_text(
        f"# Brag video (local)\n"
        f"source: {args.repo}\n"
        f"style: {req.style.value}\n"
        f"frame_rate: {24}\n"
        f"total_duration_s: {plot.total_duration_s:.0f}\n"
        f"frames_dir: {frames_dir}\n"
        f"audio_dir: {audio_dir}\n"
        f"NOTE: ffmpeg -framerate 24 -f image2 -i {frames_dir}/f_%05d.jpg -i {audio_dir}/seg_*.mp3 -c:v libx264 -c:a aac -shortest {final}\n",
        encoding="utf-8",
    )
    print(f"[local] manifest -> {final}")

    # 6) GIF (Pillow, no ffmpeg)
    gif = OUTPUT_DIR / "1_brag.gif"
    render_to_gif(plot, gif, width=960, frame_rate=12)
    print(f"[local] GIF -> {gif}")

    # 7) Cleanup old outputs
    removed = cleanup_stale([OUTPUT_DIR / "old"], max_age_days=7)
    print(f"[local] stale outputs purged: {removed}")

    print("\nTry: python demo_local.py --repo /path/to/your/repo")


if __name__ == "__main__":
    main()
