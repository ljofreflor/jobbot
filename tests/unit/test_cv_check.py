"""A CV checklist reports gaps. It does not add facts."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from jobbot.cv.check import CheckStatus, accepted_suggestion, check_cv
from jobbot.exit_codes import SUCCESS, VALIDATION_FAILURE
from jobbot.models.candidate import Candidate
from jobbot.models.job import JobPosting
from tests.fixtures.profile import sample_profile_dict


def _plain() -> Candidate:
    data = sample_profile_dict()
    data["skills"] = {"tools": ["Excel"]}
    data["experience"] = [
        {
            "id": "role",
            "company": "Servicio Neutro",
            "title": "Analista",
            "start_date": "2020-01",
            "current": True,
            "achievements": [
                {"id": "a1", "text": "Coordiné la entrega de turno entre equipos."},
            ],
        }
    ]
    return Candidate.model_validate(data)


def test_quantified_bullets_fails_when_no_bullet_has_a_number() -> None:
    report = check_cv(_plain())
    row = report.checks[0]

    assert row.id == "quantified_bullets"
    assert row.status is CheckStatus.FAIL


def test_missing_posting_term_is_listed_and_the_profile_is_not_the_store() -> None:
    job = JobPosting(
        id="J0001",
        title="Analista",
        company="Servicio Neutro",
        description="- Manejo de WordPress",
    )
    report = check_cv(_plain(), job)
    missing = next(check for check in report.checks if check.id == "hard_skills_missing")

    assert missing.status is CheckStatus.FAIL
    assert "WordPress" in missing.detail


def test_a_suggestion_that_adds_an_unknown_skill_is_dropped() -> None:
    candidate = _plain()

    assert accepted_suggestion(candidate, "- Manejo de WordPress") is None
    assert accepted_suggestion(candidate, "Acortar la primera viñeta.") == (
        "Acortar la primera viñeta."
    )
    candidate.skills.programming.append("WordPress")
    assert accepted_suggestion(candidate, "- Manejo de WordPress") == "- Manejo de WordPress"


def test_cli_exits_zero_with_the_report_and_two_when_the_job_is_missing(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "data").mkdir()
    profile = tmp_path / "data" / "profile.yaml"
    profile.write_text(
        yaml.safe_dump(_plain().model_dump(mode="json"), allow_unicode=True),
        encoding="utf-8",
    )
    (tmp_path / ".jobbot.toml").write_text(
        f'[paths]\ntemplates = "{project_root / "templates"}"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    import jobbot.cli as cli
    from jobbot.cli import run_cli
    from jobbot.db.engine import make_engine, make_session_factory
    from jobbot.jobs.repository import JobRepository

    before = profile.read_bytes()
    assert run_cli(["cv", "check"], standalone_mode=False) == SUCCESS
    out = capsys.readouterr().out
    assert "fail  quantified_bullets" in out
    assert profile.read_bytes() == before

    config = cli.load_config()
    session = make_session_factory(make_engine(config.database_path))()
    stored = JobRepository(session).upsert_external(
        JobPosting(
            id="PENDING",
            title="Analista",
            company="Servicio Neutro",
            description="- Manejo de WordPress",
        )
    )
    assert (
        run_cli(["cv", "check", "--job", stored.id], standalone_mode=False) == SUCCESS
    )
    listed = capsys.readouterr().out
    assert "hard_skills_missing" in listed
    assert "WordPress" in listed
    assert profile.read_bytes() == before
    cached = json.loads((tmp_path / "output" / "cv" / "check.json").read_text(encoding="utf-8"))
    assert any(row["id"] == "hard_skills_missing" for row in cached["checks"])

    assert run_cli(["cv", "check", "--job", "J9999"], standalone_mode=False) == VALIDATION_FAILURE
