"""Indeed hard links for `jobbot get` (#53)."""

from __future__ import annotations

from pathlib import Path

import pytest

from jobbot.adapters.indeed.jobs import (
    IndeedUrlError,
    canonical_indeed_job_url,
    job_from_indeed_hard_link,
)
from jobbot.exit_codes import SUCCESS, VALIDATION_FAILURE
from jobbot.jobs.career_page import ClosedPostingError
from jobbot.portals.detect import AtsKind

FIXTURE_APPLY = Path("tests/fixtures/jobs/indeed_viewjob_indeed_apply.html")
FIXTURE_EXTERNAL = Path("tests/fixtures/jobs/indeed_viewjob_external_ats.html")
FIXTURE_FILLED = Path("tests/fixtures/jobs/indeed_viewjob_filled.html")

TRACKED = (
    "https://cl.indeed.com/viewjob?jk=8a5fab1a7c476a97"
    "&tk=1k2s8lhchobtj801&from=jobi2a_jobmatch-reactivation-es-CL_email"
    "&rjptk=1k2s8lh04m5dl805&xpse=SoCO67I2eg10sjgVF70LbzkdCdPP"
)


def test_canonical_indeed_job_url_strips_tracking() -> None:
    assert (
        canonical_indeed_job_url(TRACKED)
        == "https://cl.indeed.com/viewjob?jk=8a5fab1a7c476a97"
    )


def test_canonical_indeed_job_url_rejects_missing_jk() -> None:
    with pytest.raises(IndeedUrlError, match="jk"):
        canonical_indeed_job_url("https://cl.indeed.com/jobs?q=data")


def test_indeed_fixture_indeed_apply_sets_applystart(
    project_root: Path,
) -> None:
    html = (project_root / FIXTURE_APPLY).read_text(encoding="utf-8")
    job = job_from_indeed_hard_link(
        "https://cl.indeed.com/viewjob?jk=abc123def456&utm_source=x",
        html=html,
    )
    assert job.source == "indeed"
    assert job.source_job_id == "abc123def456"
    assert job.url == "https://cl.indeed.com/viewjob?jk=abc123def456"
    assert job.title == "Senior Data Scientist"
    assert job.company == "Sodimac"
    assert job.ats_kind == AtsKind.INDEED.value
    assert job.ats_url == "https://cl.indeed.com/applystart?jk=abc123def456"
    assert "Python" in job.description


def test_indeed_fixture_external_ats_sets_greenhouse(
    project_root: Path,
) -> None:
    html = (project_root / FIXTURE_EXTERNAL).read_text(encoding="utf-8")
    job = job_from_indeed_hard_link(
        "https://www.indeed.com/viewjob?jk=deadbeefcafe01",
        html=html,
    )
    assert job.ats_kind == AtsKind.GREENHOUSE.value
    assert job.ats_url == "https://boards.greenhouse.io/acmelabs/jobs/12345"
    assert job.url == "https://www.indeed.com/viewjob?jk=deadbeefcafe01"


def test_indeed_fixture_filled_refuses(project_root: Path) -> None:
    html = (project_root / FIXTURE_FILLED).read_text(encoding="utf-8")
    with pytest.raises(ClosedPostingError):
        job_from_indeed_hard_link(
            "https://cl.indeed.com/viewjob?jk=abc123def456",
            html=html,
        )


def test_resolve_ats_url_prefers_external_over_indeed_page() -> None:
    from jobbot.adapters.ats.apply import resolve_ats_url
    from jobbot.models.job import JobPosting

    job = JobPosting(
        id="J0001",
        source="indeed",
        source_job_id="abc",
        url="https://cl.indeed.com/viewjob?jk=abc123def456",
        title="Role",
        company="Co",
        description="x",
        ats_url="https://boards.greenhouse.io/acmelabs/jobs/12345",
        ats_kind="greenhouse",
    )
    url, kind = resolve_ats_url(job)
    assert kind == AtsKind.GREENHOUSE
    assert "greenhouse" in (url or "")


def test_resolve_ats_url_indeed_applystart() -> None:
    from jobbot.adapters.ats.apply import resolve_ats_url
    from jobbot.models.job import JobPosting

    job = JobPosting(
        id="J0001",
        source="indeed",
        source_job_id="abc123def456",
        url="https://cl.indeed.com/viewjob?jk=abc123def456",
        title="Role",
        company="Co",
        description="x",
        ats_url="https://cl.indeed.com/applystart?jk=abc123def456",
        ats_kind="indeed",
    )
    url, kind = resolve_ats_url(job)
    assert kind == AtsKind.INDEED
    assert url == "https://cl.indeed.com/applystart?jk=abc123def456"


def _workspace(tmp_path: Path, project_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "output").mkdir(exist_ok=True)
    (tmp_path / "data" / "profile.yaml").write_text(
        (project_root / "data" / "profile.example.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (tmp_path / ".jobbot.toml").write_text(
        f'[paths]\ntemplates = "{project_root / "templates"}"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)


def test_get_indeed_fixture_stores_and_prepares(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    from jobbot.cli import run_cli
    from jobbot.config import load_config
    from jobbot.db.engine import make_engine, make_session_factory
    from jobbot.jobs.repository import JobRepository

    fixture = project_root / FIXTURE_APPLY
    code = run_cli(
        [
            "get",
            "https://cl.indeed.com/viewjob?jk=abc123def456&utm_source=mail",
            "--fixture",
            str(fixture),
        ],
        standalone_mode=False,
    )
    assert code == SUCCESS
    out = capsys.readouterr().out
    assert "Stored" in out
    assert "indeed" in out.lower() or "cl.indeed.com" in out

    config = load_config()
    session = make_session_factory(make_engine(config.database_path))()
    jobs = JobRepository(session).list_all()
    assert len(jobs) == 1
    job = jobs[0]
    assert job.source == "indeed"
    assert job.source_job_id == "abc123def456"
    assert job.url == "https://cl.indeed.com/viewjob?jk=abc123def456"
    assert job.ats_url == "https://cl.indeed.com/applystart?jk=abc123def456"
    assert (config.output_dir / "jobs" / job.id / "application").is_dir()


def test_get_indeed_without_jk_is_validation_error(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    from jobbot.cli import run_cli

    code = run_cli(
        [
            "get",
            "https://cl.indeed.com/jobs?q=data",
            "--fixture",
            str(project_root / FIXTURE_APPLY),
        ],
        standalone_mode=False,
    )
    assert code == VALIDATION_FAILURE
