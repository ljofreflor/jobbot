"""Same title and a different employer is a warning, not a profile edit."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from jobbot.adapters.diff_engine import consistency_findings, render_profile_diff, save_snapshot
from jobbot.exit_codes import SUCCESS
from jobbot.models.candidate import Candidate
from jobbot.models.external_profile import ExternalExperience, ExternalProfile
from tests.fixtures.profile import sample_profile_dict


def _candidate() -> Candidate:
    data = sample_profile_dict()
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


def test_employer_typo_is_one_company_mismatch_and_an_exact_pair_is_not() -> None:
    candidate = _candidate()
    typo = ExternalProfile(
        source="linkedin",
        experience=[ExternalExperience(company="Servicio Neutra", title="Analista")],
    )
    findings = consistency_findings(candidate, typo)

    assert len(findings) == 1
    assert findings[0].id == "experience.company_mismatch"
    assert findings[0].local == "Servicio Neutro"
    assert findings[0].remote == "Servicio Neutra"

    exact = ExternalProfile(
        source="linkedin",
        experience=[ExternalExperience(company="Servicio Neutro", title="Analista")],
    )
    assert consistency_findings(candidate, exact) == ()


def test_missing_snapshot_names_pull_and_a_warning_exits_zero(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    candidate = _candidate()
    report = render_profile_diff(candidate, tmp_path / "output", "linkedin")
    assert report == "No linkedin snapshot found. Run: jobbot linkedin pull"

    _workspace(tmp_path, project_root, monkeypatch, candidate)
    from jobbot.cli import run_cli

    missing = run_cli(["linkedin", "diff"], standalone_mode=False)
    assert missing == SUCCESS
    assert "jobbot linkedin pull" in capsys.readouterr().out

    save_snapshot(
        ExternalProfile(
            source="linkedin",
            experience=[ExternalExperience(company="Servicio Neutra", title="Analista")],
        ),
        tmp_path / "output",
    )
    profile = tmp_path / "data" / "profile.yaml"
    before = profile.read_bytes()
    warned = run_cli(["linkedin", "diff"], standalone_mode=False)
    assert warned == SUCCESS
    assert "experience.company_mismatch" in capsys.readouterr().out
    assert profile.read_bytes() == before


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
