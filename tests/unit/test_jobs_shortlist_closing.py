"""Shortlist shows a published close and a finished posting, and does not invent a date."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from jobbot.exit_codes import SUCCESS, VALIDATION_FAILURE
from jobbot.models.job import JobPosting

NOW = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)


def _workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, project_root: Path) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "profile.yaml").write_text(
        (project_root / "data" / "profile.example.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("jobbot.jobs.closing.utc_now", lambda: NOW)


def _save(job: JobPosting) -> None:
    from jobbot.cli import load_config
    from jobbot.db.engine import make_engine, make_session_factory
    from jobbot.jobs.repository import JobRepository

    config = load_config()
    session = make_session_factory(make_engine(config.database_path))()
    JobRepository(session).save(job)


def _line(out: str, job_id: str) -> str:
    return next(row for row in out.splitlines() if job_id in row)


def test_finished_phrase_is_expired_without_a_date(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    project_root: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, monkeypatch, project_root)
    _save(
        JobPosting(
            id="J0001",
            source="manual",
            title="Analyst",
            company="Estudio Neutro",
            description="El aviso dice empleo finalizado.",
        )
    )

    from jobbot.cli import run_cli

    assert run_cli(["jobs", "shortlist"], standalone_mode=False) == SUCCESS
    line = _line(capsys.readouterr().out, "J0001")
    assert "[vencido]" in line
    assert "2026" not in line
    assert "hora" not in line


def test_soon_window_is_configurable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    project_root: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, monkeypatch, project_root)
    _save(
        JobPosting(
            id="J0002",
            source="manual",
            title="Analyst",
            company="Estudio Neutro",
            closes_at=NOW + timedelta(days=5),
        )
    )
    from jobbot.cli import run_cli

    assert run_cli(["jobs", "shortlist"], standalone_mode=False) == SUCCESS
    assert "cierra pronto" not in _line(capsys.readouterr().out, "J0002")

    assert run_cli(["jobs", "shortlist", "--soon-days", "7"], standalone_mode=False) == SUCCESS
    flagged = _line(capsys.readouterr().out, "J0002")
    assert "[cierra pronto:" in flagged
    assert "2026-10-23" in flagged


def test_an_ambiguous_date_in_the_text_is_not_a_flag(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    project_root: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, monkeypatch, project_root)
    _save(
        JobPosting(
            id="J0003",
            source="manual",
            title="Analyst",
            company="Estudio Neutro",
            description="Closing Date: 10/11/2026 Central Time",
        )
    )
    from jobbot.cli import run_cli

    assert run_cli(["jobs", "shortlist"], standalone_mode=False) == SUCCESS
    line = _line(capsys.readouterr().out, "J0003")
    assert "vencido" not in line
    assert "cierra" not in line
    assert "2026-10-11" not in line
    assert "2026-11-10" not in line


def test_soon_days_below_one_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    project_root: Path,
) -> None:
    _workspace(tmp_path, monkeypatch, project_root)
    from jobbot.cli import run_cli

    assert run_cli(["jobs", "shortlist", "--soon-days", "0"], standalone_mode=False) == (
        VALIDATION_FAILURE
    )
