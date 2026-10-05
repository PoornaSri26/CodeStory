#!/usr/bin/env python3
"""
Repository Video Generator — Brag edition
Turns a repository into a punchy "brag" GIF: win centerpiece, narrated-style
scene walkthrough (features, stack, community proof) and a call-to-action.

Scene structure mirrors the brag spec (win centerpiece = "critical hit").
"""

import os
import re
import sys
from pathlib import Path
from typing import Dict, List

from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# Theme / uniform policy (single source of truth: .theme.md)
# ---------------------------------------------------------------------------

THEME = {
    "bg": (13, 16, 23),
    "panel": (22, 27, 38),
    "accent": (56, 189, 248),      # sky blue
    "win": (250, 204, 21),         # hot gold for the win centerpiece
    "text": (240, 244, 250),
    "muted": (148, 163, 184),
    "shadow": (0, 0, 0),
    "title_size": 54,
    "subtitle_size": 26,
    "kicker_size": 17,
    "stat_size": 64,
}

WIDTH, HEIGHT = 800, 450
FRAME_MS = 750

_FONT_DIRS = [
    Path(os.environ.get("ASSETS_FONT_DIR", ".")) / "fonts",
    Path(os.getcwd()) / "fonts",
    Path("C:/Windows/Fonts"),
    Path("/usr/share/fonts/truetype/dejavu"),
]

# family -> candidate font files, in preference order
_FAMILIES = {
    "title":    ["arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf"],
    "impact":   ["impact.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"],
    "subtitle": ["calibri.ttf", "arial.ttf", "DejaVuSans.ttf"],
    "kicker":   ["calibrib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"],
    "stat":     ["consolab.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"],
}
_font_cache: Dict[tuple, ImageFont.FreeTypeFont] = {}


def _font(size: int, family: str = "title") -> ImageFont.FreeTypeFont:
    key = (size, family)
    if key in _font_cache:
        return _font_cache[key]
    for name in _FAMILIES.get(family, _FAMILIES["title"]):
        for d in _FONT_DIRS:
            p = d / name
            if p.exists():
                try:
                    f = ImageFont.truetype(str(p), size)
                    _font_cache[key] = f
                    return f
                except Exception:
                    continue
    f = ImageFont.load_default()
    _font_cache[key] = f
    return f


def _wrap(draw, text, font, max_width) -> List[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if draw.textlength(t, font=font) <= max_width:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


# ---------------------------------------------------------------- background
def _gradient() -> Image.Image:
    base = Image.new("RGB", (WIDTH, HEIGHT), THEME["bg"])
    px = base.load()
    top, bottom = THEME["bg"], THEME["panel"]
    for y in range(HEIGHT):
        t = y / (HEIGHT - 1)
        c = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        for x in range(WIDTH):
            px[x, y] = c
    return base


def _glow(t: float, hot: bool) -> Image.Image:
    """Drifting accent halos; 'hot' mode (win centerpiece) burns gold."""
    layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    swing = 1 - 2 * abs(t - 0.5)                     # 1 -> 0 -> 1 over the cycle
    main = THEME["win"] if hot else THEME["accent"]
    a1 = 70 if hot else 34
    r1 = int(WIDTH * (0.42 if hot else 0.34)) + int(30 * swing)
    cx, cy = int(WIDTH * (0.5 + 0.10 * (t - 0.5) * 2)), int(HEIGHT * 0.32)
    d.ellipse([cx - r1, cy - r1, cx + r1, cy + r1], fill=(*main, a1))
    r2 = int(WIDTH * 0.20) + int(18 * (1 - swing))
    cx2, cy2 = int(WIDTH * (0.2 + 0.1 * (1 - t))), int(HEIGHT * 0.8)
    d.ellipse([cx2 - r2, cy2 - r2, cx2 + r2, cy2 + r2],
              fill=(*THEME["accent"], 22))
    return layer


def _vignette(t: float) -> Image.Image:
    layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    strength = int(38 + 26 * (1 - 2 * abs(t - 0.5)))
    d.rectangle([0, 0, WIDTH, HEIGHT], fill=(0, 0, 0, max(0, min(255, strength))))
    return layer


def _sparkle(t: float, hot: bool) -> Image.Image:
    """Tiny diagonal light streaks sweeping the frame (premium motion)."""
    layer = Image.new("RGBA", (WIDTH, HEIGHT), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    col = (*THEME["win"], 26) if hot else (*THEME["accent"], 20)
    for i in range(3):
        off = ((t * 1.6 + i * 0.33) % 1.0) * (WIDTH + 300) - 150
        d.line([(off, HEIGHT), (off + 160, 0)], fill=col, width=2)
    return layer


def background(t: float, hot: bool = False) -> Image.Image:
    img = _gradient().convert("RGBA")
    for layer in (_glow(t, hot), _sparkle(t, hot), _vignette(t)):
        img = Image.alpha_composite(img, layer)
    return img.convert("RGB")


# ---------------------------------------------------------------- generator
class RepoVideoGenerator:
    def __init__(self, repo_path: str, output_dir: str = "brag-output"):
        self.repo_path = Path(repo_path)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ info
    def extract_repo_info(self) -> Dict:
        readme_path = self.repo_path / "README.md"
        package_json_path = self.repo_path / "package.json"
        info = {"name": self.repo_path.name, "description": "", "features": [],
                "tech_stack": [], "stats": []}

        if readme_path.exists():
            md = readme_path.read_text(encoding="utf-8", errors="replace")
            m = re.search(r"#.*?\n\n(.*?)(?:\n\n|\n##)", md, re.DOTALL)
            if m:
                info["description"] = " ".join(m.group(1).split())
            sec = re.search(r"##.*[Ff]eatures.*?\n(.*?)(?:\n##|\n```|$)", md, re.DOTALL)
            if sec:
                feats = re.findall(r"^\s*[-*]\s+(.+)", sec.group(1), re.MULTILINE)
                info["features"] = [re.sub(r"`|\*\*", "", f).strip()
                                    for f in feats[:6] if len(f.strip()) > 4]
            # honest stats we can prove from the repo itself
            stars = re.findall(r"img\.shields\.io/badge/stars-([0-9.]+[km]*)", md, re.I)
            if stars:
                info["stats"].append((stars[0], "GitHub stars"))
            info["stats"].append((str(len(info["features"])), "core features"))

        if package_json_path.exists():
            try:
                pkg = json.loads(package_json_path.read_text(encoding="utf-8")) \
                    if (json := __import__("json")) else {}
                info["name"] = pkg.get("name", info["name"])
                info["description"] = pkg.get("description", info["description"])
                deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                keys = ["react", "vue", "next", "express", "typescript", "tailwind"]
                info["tech_stack"] = [k for k in keys if k in deps]
                info["stats"].append((str(len(deps)), "dependencies"))
            except Exception:
                pass
        return info

    # ----------------------------------------------------------------- frame
    def create_frame(self, text: str, kicker: str = "", sub: str = "",
                     frame_num: int = 0, total: int = 10,
                     kind: str = "scene") -> Image.Image:
        t = frame_num / max(1, total - 1)
        hot = kind == "win"
        img = background(t, hot)
        d = ImageDraw.Draw(img)

        title_f = _font(THEME["title_size"], "impact" if hot else "title")
        sub_f = _font(THEME["subtitle_size"], "subtitle")
        kick_f = _font(THEME["kicker_size"], "kicker")
        accent = THEME["win"] if hot else THEME["accent"]

        # kicker eyebrow
        y = HEIGHT // 2 - 96
        if kicker:
            kw = d.textlength(kicker.upper(), font=kick_f)
            d.text(((WIDTH - kw) / 2, y), kicker.upper(), fill=accent, font=kick_f)
            d.rectangle([(WIDTH - kw) / 2, y + 26, (WIDTH + kw) / 2, y + 28],
                        fill=(*accent, 120))
        y += 48

        # headline
        size = THEME["title_size"] + (10 if hot else 0)
        if hot:
            title_f = _font(size, "impact")
        lines = _wrap(d, text, title_f, WIDTH - 90)
        line_h = size + 12
        y = (HEIGHT - 120) // 2 - (len(lines) - 1) * line_h // 2 + 12
        for ln in lines:
            lw = d.textlength(ln, font=title_f)
            d.text(((WIDTH - lw) / 2 + 3, y + 3), ln, fill=THEME["shadow"], font=title_f)
            d.text(((WIDTH - lw) / 2, y), ln,
                   fill=THEME["win"] if hot else THEME["text"], font=title_f)
            y += line_h

        # accent underline
        uw = min(WIDTH // 3, max(120, int(max(d.textlength(l, font=title_f)
                                              for l in lines))))
        d.rectangle([(WIDTH - uw) / 2, y + 8, (WIDTH + uw) / 2, y + 12], fill=accent)

        # subtitle
        if sub:
            sw = d.textlength(sub, font=sub_f)
            d.text(((WIDTH - sw) / 2, y + 26), sub, fill=THEME["muted"], font=sub_f)

        # footer: progress + bar
        prog = f"{frame_num + 1}/{total}"
        d.text((12, HEIGHT - 36), prog, fill=THEME["muted"], font=sub_f)
        d.rectangle([12, HEIGHT - 14, WIDTH - 12, HEIGHT - 10],
                    outline=THEME["panel"])
        fill_w = int((frame_num + 1) / total * (WIDTH - 26))
        d.rectangle([12, HEIGHT - 14, 12 + fill_w, HEIGHT - 10], fill=accent)

        return img

    # -------------------------------------------------------------- slideshow
    def create_slideshow_images(self, info: Dict) -> List[Image.Image]:
        frames: List[Image.Image] = []
        plan: List[tuple] = []          # (text, kicker, sub, n_frames, kind)

        title = info["name"].replace("-", " ").replace("_", " ").title()
        plan.append((title, "logo reveal", "your project", 3, "scene"))

        # WIN CENTERPIECE — the single strongest claim
        head = None
        if info["stats"]:
            head = f"{info['stats'][0][0]} {info['stats'][0][1].upper()}"
        elif info["features"]:
            head = info["features"][0]
        elif info["description"]:
            head = info["description"][:80]
        plan.append((head or title, "critical hit", "the headline win", 4, "win"))

        desc = info["description"]
        if len(desc) > 110:
            desc = desc[:107].rstrip() + "..."
        plan.append((desc or "Built to solve real problems.", "log line",
                     "what it does", 3, "scene"))

        feats = info["features"][:5] or ["Packed with useful features"]
        for i, f in enumerate(feats):
            plan.append((f if len(f) <= 70 else f[:67] + "...",
                         f"feature {i + 1}", "why it wins", 1, "scene"))

        stack = ", ".join(info["tech_stack"][:4]) or "Modern, clean toolchain"
        plan.append((stack, "built with", "the stack", 2, "scene"))

        # community proof
        if len(info["stats"]) > 1:
            proof = "  ·  ".join(f"{v} {lbl}" for v, lbl in info["stats"][:3])
        else:
            proof = "Open source  ·  Community driven"
        plan.append((proof, "community", "the proof", 2, "scene"))

        plan.append(("Star it. Fork it. Ship it.", "join us",
                     "see it on GitHub", 2, "scene"))

        total = sum(p[3] for p in plan)
        n = 0
        for text, kicker, sub, count, kind in plan:
            for _ in range(count):
                frames.append(self.create_frame(text, kicker, sub, n, total, kind))
                n += 1
        return frames

    # ------------------------------------------------------------------ out
    def generate_gif_from_frames(self, frames: List[Image.Image]) -> str:
        gif_path = self.output_dir / "brag.gif"
        frames[0].save(gif_path, save_all=True, append_images=frames[1:],
                       duration=FRAME_MS, loop=0, optimize=True)
        print(f"GIF generated: {gif_path}")
        return str(gif_path)

    def render_gif_to_frames(self, frames: List[Image.Image]) -> None:
        for i, fr in enumerate(frames):
            fr.save(self.output_dir / f"scene{i + 1:02d}_frame{i + 1:04d}.png")
        (self.output_dir / "frame_count.txt").write_text(f"{len(frames)}\n",
                                                         encoding="utf-8")

    def generate_readme_embedding(self, gif_path: str) -> str:
        if not gif_path:
            return ""
        return ("\n## Demo\n\n"
                f"Check out the demo to see {self.repo_path.name} in action:\n\n"
                "![Demo](brag-output/brag.gif)\n\n"
                "*Auto-generated brag animation*\n")

    def generate_video(self) -> str:
        print(f"Generating brag GIF for {self.repo_path.name}...")
        info = self.extract_repo_info()
        print(f"Extracted info: {info['name']} "
              f"({len(info['features'])} features, {len(info['stats'])} stats)")
        frames = self.create_slideshow_images(info)
        print(f"Created {len(frames)} frames")
        gif = self.generate_gif_from_frames(frames)
        self.render_gif_to_frames(frames)
        return gif


def main():
    if len(sys.argv) < 2:
        print("Usage: python generate_video.py <repo_path> [output_dir]")
        sys.exit(1)
    out = sys.argv[2] if len(sys.argv) > 2 else "brag-output"
    gen = RepoVideoGenerator(sys.argv[1], out)
    gif = gen.generate_video()
    print("\n" + "=" * 50 + "\nAdd this to your README.md:\n" + "=" * 50)
    print(gen.generate_readme_embedding(gif))


if __name__ == "__main__":
    main()
