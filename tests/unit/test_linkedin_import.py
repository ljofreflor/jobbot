"""A LinkedIn snapshot can add facts. It cannot invent a date or delete a role."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from jobbot.adapters.diff_engine import save_snapshot
from jobbot.adapters.linkedin.importer import LinkedInImportError, import_plan
from jobbot.exit_codes import SUCCESS, VALIDATION_FAILURE
from jobbot.models.candidate import Candidate
from jobbot.models.external_profile import ExternalEducation, ExternalExperience, ExternalProfile
from tests.fixtures.profile import sample_profile_dict


def _candidate() -> Candidate:
    data = sample_profile_dict()
    data["personal"]["headline"] = "Analista"
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
    data["skills"] = {"tools": ["Excel"]}
    return Candidate.model_validate(data)


def _snapshot() -> ExternalProfile:
    return ExternalProfile(
        source="linkedin",
        headline="Coordinador",
        experience=[
            ExternalExperience(company="Bolsa Neutra", title="Analista", start_date="2021-04"),
            ExternalExperience(company="Otro Lugar", title="Analista", start_date="2020"),
        ],
        education=[ExternalEducation(institution="Instituto Neutro", degree="Licenciatura")],
        skills=["Excel", "Planillas"],
    )


def test_plan_adds_snapshot_facts_and_skips_a_year_only_date() -> None:
    plan = import_plan(_candidate(), _snapshot())
    texts = [change.text for change in plan.changes]

    assert "Coordinador" in texts
    assert any(text.startswith("Bolsa Neutra\tAnalista\t2021-04") for text in texts)
    assert any(text == "Instituto Neutro\tLicenciatura\t" for text in texts)
    assert "Planillas" in texts
    assert "Excel" not in texts
    assert not any("Otro Lugar" in text for text in texts)
    assert not any("Servicio Neutro" in text for text in texts)
    assert any("Otro Lugar" in warning for warning in plan.warnings)

    with pytest.raises(LinkedInImportError):
        import_plan(_candidate(), _snapshot(), section="nope")
    assert import_plan(_candidate(), ExternalProfile(source="linkedin")).warnings == (
        "sparse snapshot; nothing to import",
    )


def test_import_dry_run_keeps_the_profile_and_apply_adds_without_deleting(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    candidate = _candidate()
    _workspace(tmp_path, project_root, monkeypatch, candidate)
    save_snapshot(_snapshot(), tmp_path / "output")
    from jobbot.cli import run_cli

    profile = tmp_path / "data" / "profile.yaml"
    before = profile.read_bytes()
    dry = run_cli(["linkedin", "import"], standalone_mode=False)
    assert dry == SUCCESS
    output = capsys.readouterr().out
    assert "Coordinador" in output
    assert "Bolsa Neutra" in output
    assert profile.read_bytes() == before

    capsys.readouterr()
    scoped = run_cli(["linkedin", "import", "--section", "skills"], standalone_mode=False)
    assert scoped == SUCCESS
    scoped_out = capsys.readouterr().out
    assert "Planillas" in scoped_out
    assert "Coordinador" not in scoped_out

    monkeypatch.setattr("typer.confirm", lambda *_a, **_k: False)
    denied = run_cli(["linkedin", "import", "--apply"], standalone_mode=False)
    assert denied == SUCCESS
    assert profile.read_bytes() == before

    saved = run_cli(["linkedin", "import", "--apply", "--yes"], standalone_mode=False)
    assert saved == SUCCESS
    stored = yaml.safe_load(profile.read_text(encoding="utf-8"))
    companies = [item["company"] for item in stored["experience"]]
    assert companies == ["Servicio Neutro", "Bolsa Neutra"]
    assert stored["personal"]["headline"] == "Coordinador"
    assert "Planillas" in stored["skills"]["other"]
    profile.unlink()
    assert run_cli(["linkedin", "import"], standalone_mode=False) == VALIDATION_FAILURE


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
