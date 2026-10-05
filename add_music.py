#!/usr/bin/env python3
"""add_music: mix a background music track under a video's narration.

- loops/trims music to the video length, fades in/out
- sets music level RELATIVE to the narration (default 18 dB below)
- sidechain-ducks the music whenever the voice is present
- normalizes the final mix to a loudness target (default -14 LUFS, -1 dBTP)
- keeps video and subtitle streams untouched (no re-encode)

Usage:
  python add_music.py in.mp4 music.mp3 -o out.mp4
  python add_music.py in.mp4 music.mp3 -o out.mp4 --offset 20 --lufs -16
  python add_music.py in.mp4 --list-credits ...   (see --help)

Needs ffmpeg >= 4.4 (uses amix normalize=0) and ffprobe.
"""

import argparse
import re
import subprocess
import sys


def sh(cmd, capture=False):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("ffmpeg failed:\n" + r.stderr[-1500:])
    return r.stderr if capture else r.stdout


def duration(path):
    return float(
        sh(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "csv=p=0",
                path,
            ]
        ).strip()
    )


def lufs(path, loop_music=False):
    """Integrated loudness (LUFS) of the first audio stream."""
    out = sh(
        [
            "ffmpeg",
            "-hide_banner",
            "-nostats",
            "-i",
            path,
            "-vn",
            "-af",
            "ebur128=peak=true",
            "-f",
            "null",
            "-",
        ],
        capture=True,
    )
    m = re.findall(r"I:\s+(-?[\d.]+|-inf)\s+LUFS", out)
    return float(m[-1]) if m and m[-1] != "-inf" else -70.0


def list_credits():
    """Emit an example license/credit record for the audit trail."""
    print(
        "credit record (copy into ledger/manifest.json):\n"
        '{\n'
        '  "file": "music.mp3",\n'
        '  "title": "Track title",\n'
        '  "artist": "Artist name",\n'
        '  "licence": "CC0 | CC-BY-4.0 | ..." ,\n'
        '  "licence_url": "https://...",\n'
        '  "source_url": "https://...",\n'
        '  "retrieved": "2026-10-05",\n'
        '  "commercial_ok": true,\n'
        '  "attribution_required": true,\n'
        '  "vocals": false,\n'
        '  "proof_file": "proofs/music.mp3.png",\n'
        '  "notes": ""\n'
        '}\n'
    )


def main():
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("video")
    ap.add_argument("music")
    ap.add_argument("-o", "--out", default="with_music.mp4")
    ap.add_argument(
        "--offset",
        type=float,
        default=18.0,
        help="dB the music sits below the voice (default 18)",
    )
    ap.add_argument(
        "--lufs", type=float, default=-14.0, help="final integrated loudness target (default -14)"
    )
    ap.add_argument(
        "--fade-in", type=float, default=2.0, help="music fade-in seconds (default 2)"
    )
    ap.add_argument(
        "--fade-out",
        type=float,
        default=3.0,
        help="music fade-out seconds (default 3)",
    )
    ap.add_argument(
        "--no-duck",
        action="store_true",
        help="skip sidechain ducking",
    )
    ap.add_argument(
        "--list-credits",
        action="store_true",
        help="print the licence/credit record and exit",
    )
    a = ap.parse_args()

    if a.list_credits:
        list_credits()
        return

    dur = duration(a.video)
    voice = lufs(a.video)
    music = lufs(a.music)
    if voice < -50:  # video has no real narration -> music-only mix
        target_music, mode = -16.0, "music-only (no narration detected)"
    else:
        target_music, mode = voice - a.offset, f"under narration ({voice:.1f} LUFS voice)"
    gain = target_music - music
    print(
        f"mode: {mode}\n"
        f"music {music:.1f} LUFS -> {target_music:.1f} LUFS (gain {gain:+.1f} dB)"
    )

    fo_start = max(0.0, dur - a.fade_out)
    chain_music = (
        "[1:a]volume={gain:.2f}dB,aformat=sample_rates=44100:channel_layouts=stereo,"
        "afade=t=in:st=0:d={fade_in},afade=t=out:st={fo_start:.2f}:d={fade_out}[m]".format(
            gain=gain, fade_in=a.fade_in, fo_start=fo_start, fade_out=a.fade_out
        )
    )
    if a.no_duck or voice < -50:  # no ducking needed: single voice branch
        voice_prep = "[0:a]aformat=sample_rates=44100:channel_layouts=stereo[vo]"
        mix = "[m]anull[duck]"
        duck_chain = ""
    else:
        voice_prep = (
            "[0:a]aformat=sample_rates=44100:channel_layouts=stereo,asplit=2[vo][sc]"
        )
        mix = "[m][sc]sidechaincompress=threshold=0.02:ratio=8:attack=40:release=700:makeup=1[duck]"
        duck_chain = (
            "[m]volume={gain:.2f}dB,aformat=sample_rates=44100:channel_layouts=stereo,"
            "afade=t=in:st=0:d={fade_in},afade=t=out:st={fo_start:.2f}:d={fade_out}[m];".format(
                gain=gain, fade_in=a.fade_in, fo_start=fo_start, fade_out=a.fade_out
            )
        )
    final = (
        "[vo][duck]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[mix];"
        "[mix]loudnorm=I={lufs:.1f}:TP=-1.0:LRA=11[aout]".format(lufs=a.lufs)
    )
    fc = ";".join([chain_music, voice_prep, mix, final])

    sh(
        [
            "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            a.video,
            "-stream_loop",
            "-1",
            "-i",
            a.music,
            "-filter_complex",
            fc,
            "-map",
            "0:v",
            "-map",
            "[aout]",
            "-map",
            "0:s?",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-c:s",
            "mov_text",
            "-t",
            f"{dur:.2f}",
            a.out,
        ]
    )
    print(f"wrote {a.out}  (final loudness ≈ {lufs(a.out):.1f} LUFS)")


if __name__ == "__main__":
    main()
