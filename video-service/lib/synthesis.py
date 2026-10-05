from __future__ import annotations

import hashlib
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Callable

from .plot import Plot, Segment, Scene

# ---------------------------------------------------------------------------
# TTS bridge (stub → OpenAPI / 11Labs / Edge TTS / pyttsx3)
# ---------------------------------------------------------------------------
def tts_speak(text: str, out_path: Path) -> Path:
    """Resolve a text-to-speech file. Returns the written audio path.

    Replace with a real provider; this stub exists so the pipeline can be
    exercised end-to-end without a network voice dependency.
    """
    # TODO: wire real voice. E.g. 11labs / edge-tts / pyttsx3.
    out_path.parent.mkdir(parents=True, exist_ok=True)
    # Write a narrow-progression WAV placeholder (2s sine) so ffmpeg still encodes.
    import wave

    with wave.open(str(out_path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(b"\x00\x00" * 44100)
    return out_path


def render_audio_for(segment: Segment, out_dir: Path) -> Path:
    if segment.audio and Path(segment.audio).exists():
        return Path(segment.audio)
    key = hashlib.sha1(segment.scene.text.encode("utf-8")).hexdigest()[:10]
    path = out_dir / f"seg_{key}.mp3"
    if path.exists():
        return path
    return tts_speak(segment.scene.text, path)


# ---------------------------------------------------------------------------
# Employment cleanup: purge stale cache dirs + temp outputs older than *days*
# ---------------------------------------------------------------------------
def cleanup_stale(dirs: list[Path], max_age_days: int = 7) -> int:
    """Remove directories/functions older than *max_age_days*; returns removed count."""
    now = datetime.now().timestamp()
    removed = 0
    for d in dirs:
        if not d.exists():
            continue
        if (now - d.stat().st_mtime) > max_age_days * 86400:
            shutil.rmtree(d, ignore_errors=True)
            removed += 1
    return removed
