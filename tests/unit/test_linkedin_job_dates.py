"""Spanish card dates, a foreign city, and LinkedIn job-search cards."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from jobbot.cli import run_cli

FIXED_NOW = datetime(2026, 10, 9, tzinfo=UTC)


def _workspace(tmp_path: Path, project_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = tmp_path / "data"
    data.mkdir()
    (tmp_path / "output").mkdir()
    example = project_root / "data" / "profile.example.yaml"
    raw = yaml.safe_load(example.read_text(encoding="utf-8"))
    (data / "profile.yaml").write_text(
        yaml.safe_dump(raw, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("jobbot.adapters.linkedin.sweep._clock", lambda: FIXED_NOW)


def _stored_jobs(tmp_path: Path) -> list[dict[str, object]]:
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((tmp_path / "output" / "jobs").glob("*/job.json"))
    ]


def test_spanish_card_date_is_discarded_for_age(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    fixture = project_root / "tests/fixtures/linkedin/post_ago.txt"
    code = run_cli(
        ["linkedin", "sweep", "equipo", "--fixture", str(fixture), "--max-age-days", "30"],
        standalone_mode=False,
    )
    captured = capsys.readouterr()
    assert code == 0
    assert "descartada por antigüedad" in captured.out
    assert not _stored_jobs(tmp_path)


def test_madrid_without_a_location_line_is_discarded_for_country(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    fixture = project_root / "tests/fixtures/linkedin/post_madrid.txt"
    code = run_cli(
        ["linkedin", "sweep", "sede", "--fixture", str(fixture), "--country", "CL"],
        standalone_mode=False,
    )
    captured = capsys.readouterr()
    assert code == 0
    assert "descartada por país" in captured.out
    assert not _stored_jobs(tmp_path)


def test_job_search_saves_two_cards_and_drops_the_insight_panel(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    fixture = project_root / "tests/fixtures/linkedin/job_search.html"
    code = run_cli(
        [
            "linkedin",
            "jobs",
            "epidemiología",
            "--fixture",
            str(fixture),
            "--country",
            "CL",
        ],
        standalone_mode=False,
    )
    captured = capsys.readouterr()
    assert code == 0
    assert "Next: jobbot jobs shortlist" in captured.out
    jobs = _stored_jobs(tmp_path)
    assert len(jobs) == 2
    assert {job["url"] for job in jobs} == {
        "https://www.linkedin.com/jobs/view/43821001/",
        "https://www.linkedin.com/jobs/view/43821002/",
    }
    assert all(job["location"] for job in jobs)
    assert all(job["posted_at"] for job in jobs)
    blob = "\n".join(str(job["description"]) for job in jobs)
    assert "% de candidatos" not in blob


def test_job_search_dry_run_does_not_write(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from jobbot.config import load_config

    _workspace(tmp_path, project_root, monkeypatch)
    load_config()
    fixture = project_root / "tests/fixtures/linkedin/job_search.html"
    before = sorted(
        path.relative_to(tmp_path).as_posix()
        for path in tmp_path.rglob("*")
        if path.is_file()
    )
    code = run_cli(
        ["linkedin", "jobs", "--fixture", str(fixture), "--dry-run"],
        standalone_mode=False,
    )
    after = sorted(
        path.relative_to(tmp_path).as_posix()
        for path in tmp_path.rglob("*")
        if path.is_file()
    )
    captured = capsys.readouterr()
    assert code == 0
    assert "Dry-run: nothing written." in captured.out
    assert before == after
    assert not (tmp_path / "data" / "jobbot.sqlite").exists()
