from lib.plot import build_brag_plot
from lib.repo import RepoInfo


def _info(overrides=None):
    base = dict(name="test-repo", full_name="org/test-repo", description="Does things.",
                html_url="https://github.com/org/test-repo", stars=12345, open_issues=12,
                readme="# Test Repo\n\nDoes cool stuff.", default_branch="main")
    base.update(overrides or {})
    return RepoInfo(**base)


def test_brag_plot_has_winnable_centerpiece():
    plot = build_brag_plot(_info())
    assert plot.total_duration_s > 0
    kinds = [s.kind for s in plot.scenes]
    assert "win_centerpiece" in kinds
    assert any(s.kind == "win_centerpiece" for s in plot.scenes)


def test_brag_plot_lightweight_on_large_repo():
    # even with zero readme / zero deps (local repo), plot should still be sane
    plot = build_brag_plot(_info(dict(readme="", description="")))
    assert plot.total_duration_s >= 10
