from __future__ import annotations

from dataclasses import dataclass, field

from .repo import RepoInfo


@dataclass
class Scene:
    kind: str  # title | description | features | stack | cta | win_centerpiece
    text: str
    cue: str = ""
    duration_s: float = 4.0


@dataclass
class Segment:
    scene: Scene
    audio: str | None = None  # path to generated narration audio
    image: str | None = None  # cover image / frame to hold


@dataclass
class Plot:
    repo: RepoInfo
    scenes: list[Scene] = field(default_factory=list)
    segments: list[Segment] = field(default_factory=list)
    total_duration_s: float = 0.0

    def render_plan(self) -> str:
        lines = [f"# Plot: {self.repo.title} ({self.repo.stars} ⭐)"]
        for i, seg in enumerate(self.segments, 1):
            lines.append(f"\n## Segment {i}: {seg.scene.kind}")
            lines.append(f"- Text: {seg.scene.text[:100]}")
            lines.append(f"- Duration: {seg.scene.duration_s:.1f}s")
            if seg.audio:
                lines.append(f"- Audio: {seg.audio}")
            if seg.image:
                lines.append(f"- Image: {seg.image}")
        lines.append(f"\nTotal: {self.total_duration_s:.0f}s")
        return "\n".join(lines)


def _pick_brag_cover(repo: RepoInfo) -> str:
    """Choose a cover frame/colour for the win centerpiece."""
    return repo.html_url or "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' width='1920' height='1080'><rect fill='#1a1a2e'/></svg>"


def build_brag_plot(repo: RepoInfo, max_frames: int = 40) -> Plot:
    scenes: list[Scene] = []
    segments: list[Segment] = []
    total = 0.0

    # 0. Intro cover (branded slate)
    scenes.append(Scene(kind="title", text=repo.title, cue="logo reveal", duration_s=2.0))
    segments.append(Segment(Scene(kind="title", text=repo.title, cue="logo reveal", duration_s=2.0)))
    total += 2.0

    # 1. The Brag (win centerpiece) — 20-30% of total duration
    headline = _brag_headline(repo, max_frames)
    # keep the blast-off short: 5s
    scenes.append(Scene(kind="win_centerpiece", text=headline, cue="critical hit", duration_s=5.0))
    segments.append(Segment(Scene(kind="win_centerpiece", text=headline, cue="critical hit", duration_s=5.0)))
    total += 5.0

    # 2. Description — what it does
    desc = (repo.description or "").strip()
    if not desc:
        desc = f"{repo.title} is an open-source project that solves real problems with clean code."
    scenes.append(Scene(kind="description", text=desc[:180], cue="log line", duration_s=4.0))
    segments.append(Segment(Scene(kind="description", text=desc[:180], cue="log line", duration_s=4.0)))
    total += 4.0

    # 3. Features — pull from README bullet points
    feats = _features_from_readme(repo)
    for i, feat in enumerate(feats[:5]):
        scenes.append(Scene(kind="features", text=feat, cue=f"feature {i+1}", duration_s=4.0))
        segments.append(Segment(Scene(kind="features", text=feat, cue=f"feature {i+1}", duration_s=4.0)))
        total += 4.0

    # 4. Tech stack
    deps = _tech_stack(repo)
    stack = ", ".join(deps[:4]) if deps else "Modern, dependency-light toolchain"
    scenes.append(Scene(kind="stack", text=stack, cue="built with", duration_s=4.0))
    segments.append(Segment(Scene(kind="stack", text=stack, cue="built with", duration_s=4.0)))
    total += 4.0

    # 5. Activity proof (PRs / stars / issues)
    if repo.open_prs:
        proof = f"Over {repo.stars} ⭐, {repo.open_issues} open issues, {len(repo.open_prs)} open PRs."
    else:
        proof = f"Over {repo.stars} ⭐ {repo.full_name}."
    scenes.append(Scene(kind="features", text=proof, cue="community", duration_s=3.0))
    segments.append(Segment(Scene(kind="features", text=proof, cue="community", duration_s=3.0)))
    total += 3.0

    # 6. CTA
    scenes.append(Scene(kind="cta", text="See it in action — star it & contribute.", cue="join us", duration_s=4.0))
    segments.append(Segment(Scene(kind="cta", text="See it in action — star it & contribute.", cue="join us", duration_s=4.0)))
    total += 4.0

    return Plot(repo=repo, scenes=scenes, segments=segments, total_duration_s=total)


def _brag_headline(repo: RepoInfo, max_frames: int) -> str:
    """For a brag video, the headline is the repo's single strongest claim."""
    # Heuristic picks the strongest of: stars, PRs, README first line, language.
    candidates = [f"{repo.stars} ⭐ {repo.full_name.split('/')[-1]}" if repo.stars else None]
    if repo.description:
        candidates.append(repo.description[:70])
    return candidates[0] or repo.title


def _features_from_readme(repo: RepoInfo) -> list[str]:
    if not repo.readme:
        return []
    import re

    # Pulls "- item" bullets, up to 5.
    bullets = re.findall(r"^\s*[-*]\s+(.+)$", repo.readme, re.MULTILINE)
    return [b.strip()[:120] for b in bullets[:5] if len(b.strip()) > 8]


def _tech_stack(repo: RepoInfo) -> list[str]:
    pkg = repo.package_json
    if isinstance(pkg, dict):
        deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        key = ["react", "vue", "typescript", "express", "next", "fastapi", "tokio", "prisma"]
        return [k for k in key if k in deps]
    return []
