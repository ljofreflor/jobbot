"""`jobbot get` stores an Indeed hard link and stops before submit."""

from __future__ import annotations

from pathlib import Path

import pytest

from jobbot.exit_codes import SUCCESS, VALIDATION_FAILURE


def _workspace(tmp_path: Path, project_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = tmp_path / "data"
    data.mkdir(exist_ok=True)
    (data / "profile.yaml").write_text(
        (project_root / "data" / "profile.example.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)


def _write_fixture(tmp_path: Path, extra: str = "") -> Path:
    html = f"""<!DOCTYPE html><html><body>
    <h1 data-testid="jobsearch-JobInfoHeader-title">Senior Data Scientist</h1>
    <div data-testid="inlineHeader-companyName">Sodimac</div>
    <div data-testid="jobsearch-JobInfoHeader-locationText">Santiago, Chile</div>
    <div id="jobDescriptionText"><p>Python and SQL.</p></div>
    {extra}
    </body></html>"""
    path = tmp_path / "viewjob.html"
    path.write_text(html, encoding="utf-8")
    return path


def _patch_browser(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    opened: list[str] = []
    monkeypatch.setattr("webbrowser.open", lambda url: opened.append(url) or True)
    return opened


def test_dry_run_shows_the_job_and_writes_nothing(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    fixture = _write_fixture(tmp_path)
    from jobbot.cli import run_cli

    code = run_cli(
        [
            "get",
            "https://cl.indeed.com/viewjob?jk=abc123&from=email",
            "--fixture",
            str(fixture),
        ],
        standalone_mode=False,
    )
    out = capsys.readouterr().out

    assert code == SUCCESS
    assert "Senior Data Scientist" in out
    assert "Sodimac" in out
    assert not (tmp_path / "data" / "jobbot.sqlite").exists()
    assert not (tmp_path / "output" / "jobs").exists()


def test_jobs_get_is_the_same_command(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    fixture = _write_fixture(tmp_path)
    from jobbot.cli import run_cli

    code = run_cli(
        [
            "jobs",
            "get",
            "https://cl.indeed.com/viewjob?jk=abc123",
            "--fixture",
            str(fixture),
        ],
        standalone_mode=False,
    )

    assert code == SUCCESS
    assert not (tmp_path / "output" / "jobs").exists()


def test_apply_stores_a_canonical_job(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    fixture = _write_fixture(tmp_path)
    from jobbot.cli import run_cli
    from jobbot.jobs.repository import JobRepository

    code = run_cli(
        [
            "get",
            "https://cl.indeed.com/viewjob?jk=abc123&from=email&tk=xyz",
            "--fixture",
            str(fixture),
            "--apply",
        ],
        standalone_mode=False,
    )
    out = capsys.readouterr().out

    assert code == SUCCESS
    assert "J0001" in out
    stored = tmp_path / "output" / "jobs" / "J0001" / "job.json"
    assert stored.is_file()
    assert not (tmp_path / "output" / "jobs" / "J0001" / "jobs").exists()

    from jobbot.config import load_config
    from jobbot.db.engine import make_engine, make_session_factory

    config = load_config()
    session = make_session_factory(make_engine(config.database_path))()
    job = JobRepository(session).get("J0001")
    assert job is not None
    assert job.source == "indeed"
    assert job.source_job_id == "abc123"
    assert job.url == "https://cl.indeed.com/viewjob?jk=abc123"
    assert job.ats_url == "https://cl.indeed.com/applystart?jk=abc123"


def test_a_url_without_jk_is_rejected(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    from jobbot.cli import run_cli

    code = run_cli(
        ["get", "https://cl.indeed.com/viewjob?foo=bar"],
        standalone_mode=False,
    )

    assert code == VALIDATION_FAILURE
    assert not (tmp_path / "output" / "jobs").exists()


def test_a_non_indeed_host_is_rejected(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    from jobbot.cli import run_cli

    code = run_cli(
        ["get", "https://www.linkedin.com/jobs/view/123"],
        standalone_mode=False,
    )

    assert code == VALIDATION_FAILURE
    assert not (tmp_path / "output" / "jobs").exists()


def test_an_external_ats_is_what_gets_stored(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    fixture = _write_fixture(
        tmp_path,
        extra=(
            '<a href="https://boards.greenhouse.io/acme/jobs/4001">'
            "Apply on company site</a>"
        ),
    )
    from jobbot.cli import run_cli
    from jobbot.config import load_config
    from jobbot.db.engine import make_engine, make_session_factory
    from jobbot.jobs.repository import JobRepository

    assert (
        run_cli(
            [
                "get",
                "https://cl.indeed.com/viewjob?jk=abc123",
                "--fixture",
                str(fixture),
                "--apply",
            ],
            standalone_mode=False,
        )
        == SUCCESS
    )
    config = load_config()
    session = make_session_factory(make_engine(config.database_path))()
    job = JobRepository(session).get("J0001")
    assert job is not None
    assert job.ats_url == "https://boards.greenhouse.io/acme/jobs/4001"
    assert "indeed.com" not in (job.ats_url or "")


def test_an_expired_posting_is_not_stored(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    fixture = _write_fixture(tmp_path, extra="<p>This job has expired on Indeed.</p>")
    from jobbot.cli import run_cli

    code = run_cli(
        [
            "get",
            "https://cl.indeed.com/viewjob?jk=abc123",
            "--fixture",
            str(fixture),
            "--apply",
        ],
        standalone_mode=False,
    )
    captured = capsys.readouterr()
    text = captured.out + captured.err

    assert code == VALIDATION_FAILURE
    assert "expir" in text.casefold()
    assert not (tmp_path / "output" / "jobs").exists()


def test_apply_dry_run_does_not_open_a_browser(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    fixture = _write_fixture(tmp_path)
    opened = _patch_browser(monkeypatch)
    from jobbot.cli import run_cli

    assert (
        run_cli(
            [
                "get",
                "https://cl.indeed.com/viewjob?jk=abc123",
                "--fixture",
                str(fixture),
                "--apply",
            ],
            standalone_mode=False,
        )
        == SUCCESS
    )
    code = run_cli(["application", "apply", "J0001"], standalone_mode=False)

    assert code == SUCCESS
    assert opened == []


def test_application_apply_opens_indeed_apply_and_does_not_submit(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    fixture = _write_fixture(tmp_path)
    opened = _patch_browser(monkeypatch)
    from jobbot.cli import run_cli

    assert (
        run_cli(
            [
                "get",
                "https://cl.indeed.com/viewjob?jk=abc123",
                "--fixture",
                str(fixture),
                "--apply",
            ],
            standalone_mode=False,
        )
        == SUCCESS
    )
    code = run_cli(
        ["application", "apply", "J0001", "--apply", "--yes"],
        standalone_mode=False,
    )

    assert code == SUCCESS
    assert opened == ["https://cl.indeed.com/applystart?jk=abc123"]


def test_application_apply_opens_the_external_ats(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    fixture = _write_fixture(
        tmp_path,
        extra=(
            '<a href="https://boards.greenhouse.io/acme/jobs/4001">'
            "Apply on company site</a>"
        ),
    )
    opened = _patch_browser(monkeypatch)
    from jobbot.cli import run_cli

    assert (
        run_cli(
            [
                "get",
                "https://cl.indeed.com/viewjob?jk=abc123",
                "--fixture",
                str(fixture),
                "--apply",
            ],
            standalone_mode=False,
        )
        == SUCCESS
    )
    code = run_cli(
        ["application", "apply", "J0001", "--apply", "--yes"],
        standalone_mode=False,
    )

    assert code == SUCCESS
    assert opened == ["https://boards.greenhouse.io/acme/jobs/4001"]
