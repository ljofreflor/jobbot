"""A cover letter restates profile facts. An invented name or number is dropped."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from jobbot.applications.cover_letter import choose_draft, draft_cover_letter, unsupported_tokens
from jobbot.exit_codes import SUCCESS, USER_CANCEL
from jobbot.models.candidate import Candidate
from jobbot.models.job import JobPosting
from tests.fixtures.profile import sample_profile_dict


def _candidate(*, summary: str | None) -> Candidate:
    data = sample_profile_dict()
    data["summary"] = summary
    data["experience"] = [
        {
            "id": "role",
            "company": "Servicio Neutro",
            "title": "Analista",
            "start_date": "2020-01",
            "current": True,
            "achievements": [{"id": "a1", "text": "Cerré 12 turnos."}],
        }
    ]
    return Candidate.model_validate(data)


def _job() -> JobPosting:
    return JobPosting(
        id="J0001",
        title="Coordinador",
        company="Bolsa Neutra",
        description="El aviso pide 40 horas y nombra Kubernetes.",
    )


def test_draft_uses_profile_facts_and_drops_an_invented_proposal() -> None:
    candidate = _candidate(summary=None)
    job = _job()
    letter = draft_cover_letter(candidate, job)

    assert "Coordinador" in letter
    assert "Bolsa Neutra" in letter
    assert "Cerré 12 turnos." in letter
    assert "Kubernetes" not in letter
    assert "40" not in letter
    assert unsupported_tokens(letter, candidate, job) == ()

    invented = "Postulo al cargo y domino Kubernetes desde hace 99 meses."
    assert "Kubernetes" in unsupported_tokens(invented, candidate, job)
    assert "99" in unsupported_tokens(invented, candidate, job)
    assert "Kubernetes" not in choose_draft(candidate, job, invented)

    backed = "El perfil registra el cargo de Analista en Servicio Neutro."
    assert choose_draft(candidate, job, backed).strip() == backed


def test_a_summary_is_used_when_present_and_absent_summary_still_writes() -> None:
    job = _job()
    with_summary = draft_cover_letter(_candidate(summary="Ordené el archivo de turnos."), job)
    without = draft_cover_letter(_candidate(summary=None), job)

    assert "Ordené el archivo de turnos." in with_summary
    assert "Cerré 12 turnos." not in with_summary
    assert "Cerré 12 turnos." in without


def test_cover_letter_writes_the_file_and_records_the_manifest_on_apply(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch, _candidate(summary=None))
    import jobbot.cli as cli
    from jobbot.cli import run_cli
    from jobbot.db.engine import make_engine, make_session_factory
    from jobbot.jobs.repository import JobRepository

    config = cli.load_config()
    session = make_session_factory(make_engine(config.database_path))()
    JobRepository(session).save(_job())
    package = tmp_path / "output" / "jobs" / "J0001" / "application"
    package.mkdir(parents=True)
    manifest = package / "manifest.json"
    manifest.write_text(json.dumps({"job_id": "J0001", "files": []}) + "\n", encoding="utf-8")

    dry = run_cli(["application", "cover-letter", "J0001"], standalone_mode=False)
    assert dry == SUCCESS
    letter = tmp_path / "output" / "jobs" / "J0001" / "cover-letter.txt"
    assert letter.is_file()
    assert "Cerré 12 turnos." in letter.read_text(encoding="utf-8")
    assert "cover_letter" not in json.loads(manifest.read_text(encoding="utf-8"))
    assert "cover-letter.txt" in capsys.readouterr().out

    monkeypatch.setattr("typer.confirm", lambda *_a, **_k: False)
    denied = run_cli(["application", "cover-letter", "J0001", "--apply"], standalone_mode=False)
    assert denied == USER_CANCEL
    assert "cover_letter" not in json.loads(manifest.read_text(encoding="utf-8"))

    saved = run_cli(
        ["application", "cover-letter", "J0001", "--apply", "--yes"],
        standalone_mode=False,
    )
    assert saved == SUCCESS
    recorded = json.loads(manifest.read_text(encoding="utf-8"))
    assert recorded["cover_letter"] == str(letter)


def _workspace(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    candidate: Candidate,
) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "profile.yaml").write_text(
        yaml.safe_dump(candidate.model_dump(mode="json"), allow_unicode=True),
        encoding="utf-8",
    )
    (tmp_path / ".jobbot.toml").write_text(
        f'[paths]\ntemplates = "{project_root / "templates"}"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
