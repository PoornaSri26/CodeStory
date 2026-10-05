from schemas.video import Job, JobRequest, JobSummary, Style


def test_style_enum_roundtrip():
    assert Style.Brag.value == "brag"
    assert Style.Kando.value == "kando"
    assert JobRequest(style=Style.Kando).style == Style.Kando


def test_job_summary_fields():
    j = JobSummary(
        job_id="1", repo="org/repo", style=Style.Brag, status="finished",
        progress=1.0, message="done", duration_seconds=30.0, output_url="/api/videos/1/file",
        error=None, created_at="2026-10-05T00:00:00Z", updated_at="2026-10-05T00:00:30Z",
    )
    assert j.job_id == "1"
    assert j.status == "finished"
    assert j.output_url == "/api/videos/1/file"
