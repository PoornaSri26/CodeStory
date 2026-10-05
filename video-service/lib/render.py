from __future__ import annotations

import math
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .plot import Plot, Scene

# ---------------------------------------------------------------- theme tokens (mirrors .theme.md)
BG       = (14,  17,  22)       # deep slate
PANEL    = (18,  22,  30)       # framed panel
ACCENT   = (56,  189, 248)      # neon sky-blue
ACCENT2  = (45,  212, 191)      # teal glow
MUTED    = (148, 163, 184)      # slate-400
WHITE    = (240, 240, 245)
VIGNETTE = (11,  14,  20)       # darkest edge

# ---------------------------------------------------------------- fonts


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    """Try several font paths; degrade gracefully to Pillow default."""
    import os
    candidates_bold = [
        "DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/calibrib.ttf",
    ]
    candidates_reg = [
        "DejaVuSans.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/calibri.ttf",
    ]
    asset_dir = os.environ.get("ASSETS_FONT_DIR", "")
    pool = candidates_bold if bold else candidates_reg
    if asset_dir:
        pool = [str(Path(asset_dir) / "fonts" / Path(p).name) for p in pool] + pool
    for p in pool:
        try:
            return ImageFont.truetype(p, size)
        except Exception:
            continue
    return ImageFont.load_default()


# ---------------------------------------------------------------- primitives

def _lerp(a, b, t):
    return a + (b - a) * t


def _lerp_rgb(c1, c2, t):
    return tuple(int(_lerp(c1[i], c2[i], t)) for i in range(3))


def _make_background(w: int, h: int) -> Image.Image:
    """4-corner radial gradient: dark slate core → near-black vignette edges."""
    img = Image.new("RGB", (w, h))
    px = img.load()
    cx, cy = w / 2, h / 2
    max_r = math.hypot(cx, cy)
    for y in range(h):
        for x in range(w):
            r = math.hypot(x - cx, y - cy) / max_r
            r = min(1.0, r * 1.35)
            c = _lerp_rgb(PANEL, VIGNETTE, r)
            px[x, y] = c
    return img


def _dot_grid(img: Image.Image, spacing: int = 40, dot_size: int = 1, alpha: int = 18) -> Image.Image:
    """Subtle dot grid overlay for depth."""
    w, h = img.size
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(overlay)
    for y in range(0, h, spacing):
        for x in range(0, w, spacing):
            d.ellipse([x - dot_size, y - dot_size, x + dot_size, y + dot_size],
                      fill=(*MUTED, alpha))
    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font, max_width: int) -> list[str]:
    words = text.split()
    if not words:
        return [""]
    lines, cur = [], words[0]
    for w in words[1:]:
        trial = cur + " " + w
        if draw.textlength(trial, font=font) <= max_width:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


def _draw_accent_bar(img: Image.Image, accent: tuple) -> None:
    """Top gradient accent bar, brightest at center."""
    w, _ = img.size
    bar = Image.new("RGBA", (w, 4), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bar)
    for x in range(w):
        t = abs(x / w - 0.5) * 2
        a = int(255 * (1 - t * 0.6))
        bd.point([(x, 0), (x, 1), (x, 2), (x, 3)], fill=(*accent, a))
    base_crop = img.convert("RGBA").crop((0, 0, w, 4))
    img.paste(Image.alpha_composite(base_crop, bar).convert("RGB"), (0, 0))


def _draw_accent_divider(img: Image.Image, x: int, y: int, w: int, accent: tuple) -> None:
    """Short glowing horizontal divider line."""
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    for spread in (4, 3, 2, 1):
        a = int(40 * spread)
        od.line([(x, y), (x + w, y)], fill=(*accent, a), width=spread * 2)
    od.line([(x, y), (x + w, y)], fill=(*accent, 255), width=2)
    combined = Image.alpha_composite(img.convert("RGBA"), overlay)
    img.paste(combined.convert("RGB"))


def _draw_progress(img: Image.Image, idx: int, total: int, font, accent: tuple) -> None:
    """Bottom progress bar + segment counter."""
    w, h = img.size
    bar_y = h - 8
    bar_w = int(w * (idx + 1) / max(total, 1))
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rectangle([(0, bar_y), (w, bar_y + 4)], fill=(*PANEL, 180))
    od.rectangle([(0, bar_y), (bar_w, bar_y + 4)], fill=(*accent, 200))
    label = f"{idx + 1} / {total}"
    od.text((w - 80, h - 32), label, font=font, fill=(*MUTED, 180))
    combined = Image.alpha_composite(img.convert("RGBA"), overlay)
    img.paste(combined.convert("RGB"))


# ---------------------------------------------------------------- scene kinds → layout

_KIND_ACCENT = {
    "title":           ACCENT,
    "win_centerpiece": ACCENT2,
    "description":     ACCENT,
    "features":        ACCENT2,
    "stack":           ACCENT,
    "cta":             ACCENT2,
}

_KIND_BADGE = {
    "title":           "⚡",
    "win_centerpiece": "🏆",
    "description":     "📝",
    "features":        "✦",
    "stack":           "🛠",
    "cta":             "🚀",
}


def frame_for(scene: Scene, idx: int, total: int, width: int = 1280, height: int = 720) -> Image.Image:
    """Render a premium-branded scene frame."""
    # 1. Radial-vignette background + dot grid
    img = _make_background(width, height)
    img = _dot_grid(img)

    accent = _KIND_ACCENT.get(scene.kind, ACCENT)
    badge  = _KIND_BADGE.get(scene.kind, "")

    font_title    = _font(52, bold=True)
    font_subtitle = _font(26)
    font_small    = _font(18)
    font_badge    = _font(36)

    # 2. Top accent bar
    _draw_accent_bar(img, accent)

    # 3. Compute wrapped lines & card geometry
    pad_x = 100
    card_w = width - pad_x * 2

    tmp_draw = ImageDraw.Draw(img.copy())
    lines = _wrap_text(tmp_draw, scene.text, font_title, card_w - 80)
    line_h = int(font_title.size * 1.35)
    cue_block = 60 if scene.cue else 0
    block_h = len(lines) * line_h + cue_block + 40

    card_x = pad_x
    card_y = (height - block_h) // 2 - 20
    card_h = block_h + 56

    # 4. Glassmorphism card
    card_overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    cod = ImageDraw.Draw(card_overlay)
    cod.rounded_rectangle(
        [card_x, card_y, card_x + card_w, card_y + card_h],
        radius=20,
        fill=(*PANEL, 160),
        outline=(*accent, 70),
        width=1,
    )
    img = Image.alpha_composite(img.convert("RGBA"), card_overlay).convert("RGB")

    draw = ImageDraw.Draw(img, "RGBA")

    # 5. Badge emoji (top-left of card)
    draw.text((card_x + 18, card_y + 12), badge, font=font_badge, fill=(*accent, 230))

    # 6. Title lines with shadow
    ty = card_y + 22
    for line in lines:
        lw = draw.textlength(line, font=font_title)
        tx = (width - lw) / 2
        draw.text((tx + 2, ty + 2), line, font=font_title, fill=(0, 0, 0, 100))
        draw.text((tx, ty), line, font=font_title, fill=(*WHITE, 255))
        ty += line_h

    # 7. Accent divider + cue label
    if scene.cue:
        div_y = ty + 8
        div_x = width // 2 - 80
        _draw_accent_divider(img, div_x, div_y, 160, accent)
        draw2 = ImageDraw.Draw(img, "RGBA")
        cue_text = f"▶  {scene.cue.upper()}"
        cw = draw2.textlength(cue_text, font=font_subtitle)
        draw2.text(((width - cw) / 2, div_y + 14), cue_text, font=font_subtitle, fill=(*accent, 210))

    # 8. Bottom progress bar
    _draw_progress(img, idx, total, font_small, accent)

    return img


# ---------------------------------------------------------------- render pipelines

def render_to_webm(plot: Plot, out, frame_rate: int = 24, bitrate: int = 3500, progress_cb=None):
    """Render storyboard frames into a video source. Returns frames dir."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)

    total = len(plot.segments)
    frame_fn = lambda i: frame_for(plot.segments[i].scene, i, total)

    if _ffmpeg_available():
        frames_dir = _mp4_write(out, total, frame_rate, 1280, 720, frame_fn)
    else:
        frames_dir = out.parent / f".{out.stem}_frames_{hash(out)}"
        frames_dir.mkdir(parents=True, exist_ok=True)
        for i in range(total):
            img = frame_fn(i)
            img.save(frames_dir / f"f_{i:05d}.jpg", quality=92)
        import json as _json
        (frames_dir / "manifest.json").write_text(
            _json.dumps({"fps": frame_rate, "width": 1280, "height": 720, "frames": total}),
            encoding="utf-8",
        )
        out.unlink(missing_ok=True)
        if progress_cb:
            progress_cb(total, total)

    return frames_dir


def render_to_gif(plot: Plot, out, width: int = 960, frame_rate: int = 24):
    """Render the storyboard into an animated GIF (no external encoder required)."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    total = len(plot.segments)
    tmp_dir = Path(tempfile.mkdtemp(prefix="vg_"))
    for i, seg in enumerate(plot.segments):
        img = frame_for(seg.scene, i, total, width=width, height=int(width * 9 / 16))
        img.save(tmp_dir / f"f_{i:04d}.png")
    frames = [Image.open(f) for f in sorted(tmp_dir.glob("*.png"))]
    if not frames:
        raise RuntimeError("no frames rendered for GIF")
    fps = int(frame_rate) or 24
    frames[0].save(
        str(out), save_all=True, append_images=frames[1:],
        duration=[int(1000 / fps)] * len(frames), loop=0,
    )
    return out


def _mp4_write(out_path: Path, frame_count: int, fps: float, width: int, height: int, frame_fn):
    tmp_frames = out_path.parent / f".tmp_{out_path.name}_frames"
    tmp_frames.mkdir(parents=True, exist_ok=True)
    for i in range(frame_count):
        img = frame_fn(i)
        img.save(tmp_frames / f"f_{i:05d}.jpg", quality=92)
    return tmp_frames


def _ffmpeg_available() -> bool:
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True, timeout=5)
        return True
    except Exception:
        return False


def mux(plot: Plot, video, audio=None, out=None, frame_rate=None, bitrate=None):
    """Combine rendered video + narration into one MP4 (no-op placeholder)."""
    out = Path(out) if out else None
    if video is None:
        raise ValueError("missing video source")
    if out is None:
        return video
    return out
