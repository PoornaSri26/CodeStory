from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import base64
import json
import os
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

GH_BASE = "https://api.github.com/repos"
USER_AGENT = "repo-video-generator/1.0 (personal)"
# Be nice to the GitHub search API: 1 req / 2s is the safe sustainable rate.
REQUEST_DELAY = 2.0


def _github_token() -> str | None:
    return os.environ.get("GITHUB_TOKEN")  # noqa: F401  (import os above)


@dataclass
class RepoInfo:
    name: str
    full_name: str
    path: str | None = None
    description: str = ""
    html_url: str = ""
    stars: int = 0
    forks: int = 0
    language: str = ""
    default_branch: str = "main"
    readme: str = ""
    readme_html: str = ""
    package_json: dict[str, Any] = field(default_factory=dict)
    topics: list[str] = field(default_factory=list)
    open_prs: list[dict[str, Any]] = field(default_factory=list)
    open_issues: int = 0
    last_updated: str = ""
    error: str | None = None

    @property
    def title(self) -> str:
        return self.name.replace("-", " ").replace("_", " ").title()

    @property
    def short_desc(self) -> str:
        return self.description or f"An open-source {self.name} project."


def _delay():
    """Rate-limit back-off: sleeps one interval between aggressive API calls."""
    time.sleep(REQUEST_DELAY)


class RepoFetcher:
    def __init__(self, token: str | None = None):
        self._sess = requests.Session()
        retries = Retry(
            total=5,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET"],
        )
        self._sess.mount("https://", HTTPAdapter(max_retries=retries))
        self._sess.headers.update({"Accept": "application/vnd.github+json"})
        if token:
            self._sess.headers["Authorization"] = f"Bearer {token}"
        self._sess.headers["User-Agent"] = USER_AGENT

    def fetch(self, repo: str) -> RepoInfo:
        full_name = self._normalize(repo)
        info = RepoInfo(name=full_name.split("/")[-1], full_name=full_name)
        try:
            info = self._fetch_api(info)
        except Exception as exc:  # noqa: BLE001
            info.error = str(exc)
        return info

    def _normalize(self, repo: str) -> str:
        repo = repo.strip().rstrip("/")
        m = re.match(r"^(?:https?://)?github\.com/([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)(?:/.*)?$", repo)
        if m:
            return m.group(1)
        return repo

    def _fetch_api(self, info: RepoInfo) -> RepoInfo:
        url = f"{GH_BASE}/{info.full_name}"
        for attempt in range(3):
            r = self._sess.get(url, timeout=20)
            if r.status_code == 403 and "rate limit" in r.text.lower():
                reset = r.headers.get("X-RateLimit-Reset")
                wait = 60 if not reset else int(reset) - int(time.time()) + 10
                _delay()  # respect the rate window
                continue
            r.raise_for_status()
            data = r.json()
            break
        else:
            raise RuntimeError("GitHub API rate limited")

        info.description = data.get("description") or ""
        info.html_url = data.get("html_url") or ""
        info.stars = data.get("stargazers_count") or 0
        info.forks = data.get("forks_count") or 0
        info.language = data.get("language") or ""
        info.default_branch = data.get("default_branch") or "main"
        info.open_issues = data.get("open_issues_count") or 0
        info.last_updated = data.get("updated_at") or ""

        # README (GitHub-flavored Markdown)
        try:
            rd = self._sess.get(f"{url}/readme", timeout=20).json()
            import base64

            info.readme = base64.b64decode(rd.get("content") or "").decode("utf-8", errors="replace")
            info.readme_html = base64.b64decode(rd.get("html_url", ""))  # placeholder
        except Exception:
            info.readme = ""

        # package.json / pyproject.toml / etc.
        pkg = self._try_fetch(f"{url}/package", timeout=10)
        if pkg is None:
            pkg = self._try_fetch(f"{url}/pyproject", timeout=10)
        if isinstance(pkg, dict):
            info.package_json = pkg

        # Topics
        try:
            t = self._sess.get(f"{url}/topics", timeout=10).json()
            info.topics = t.get("names") or []
        except Exception:
            pass

        # Open PRs / issues (capped, shallow)
        try:
            prs = self._sess.get(f"{url}/pulls?state=open&per_page=12", timeout=20).json()
            if isinstance(prs, list):
                info.open_prs = prs[:12]
        except Exception:
            pass

        _delay()
        return info

    def _try_fetch(self, url: str, timeout: int = 10):
        for attempt in range(2):
            try:
                r = self._sess.get(url, timeout=timeout)
                if r.status_code == 200 and r.content:
                    try:
                        return r.json()
                    except ValueError:
                        return r.text
                if r.status_code in (403, 404):
                    return None
            except Exception:
                pass
        return None


# ---------------------------------------------------------------------------
# Local path variant
# ---------------------------------------------------------------------------


class LocalRepoFetcher:
    """Turns a local directory into a 'repo info' bag without network I/O."""

    def fetch(self, path: str) -> RepoInfo:
        base = Path(path).expanduser().resolve()
        if not base.exists():
            raise FileNotFoundError(f"Path not found: {base}")

        info = RepoInfo(name=base.name, full_name=base.name, html_url=str(base), path=str(base))

        readme = base / "README.md"
        if readme.exists():
            info.readme = readme.read_text(encoding="utf-8", errors="replace")

        pkg = base / "package.json"
        if pkg.exists():
            import json

            try:
                info.package_json = json.loads(pkg.read_text(encoding="utf-8"))
                info.language = "JavaScript/TypeScript"
            except Exception:
                pass

        return info
