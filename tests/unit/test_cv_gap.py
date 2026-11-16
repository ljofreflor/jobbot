"""Posting terms the profile already covers stay matched. The rest stay questions."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from jobbot.cv.gap import GapStatus, gap_report
from jobbot.exit_codes import SUCCESS
from jobbot.models.candidate import Candidate
from jobbot.models.job import JobPosting
from tests.fixtures.profile import sample_profile_dict

_JD = """\
- Manejo de PostgreSQL
- Manejo de Excel
- Manejo de ventilación mecánica
- Habilidad de comunicación
"""


def _candidate() -> Candidate:
    data = sample_profile_dict()
    data["skills"] = {"tools": ["postgres", "Excel"]}
    data["summary"] = "Coordina turnos."
    return Candidate.model_validate(data)


def _job() -> JobPosting:
    return JobPosting(
        id="J0001",
        title="Analista",
        company="Servicio Neutro",
        description=_JD,
    )


def test_two_hard_terms_match_and_one_stays_a_gap() -> None:
    report = gap_report(_candidate(), _job())
    hard = [term for term in report.terms if term.kind == "hard"]

    assert report.matched == 2
    assert report.missing == 1
    by_term = {term.term.casefold(): term for term in hard}
    assert by_term["postgresql"].status is GapStatus.MATCHED
    assert by_term["postgresql"].evidence == "skill:postgres"
    assert by_term["excel"].status is GapStatus.MATCHED
    start, end = by_term["excel"].span
    assert _JD[start:end].casefold() == "excel"
    missing = [term for term in hard if term.status is GapStatus.GAP]
    assert len(missing) == 1
    assert "ventil" in missing[0].term.casefold()
    assert missing[0].evidence == ""


def test_soft_terms_are_listed_apart_and_not_counted_as_hard_gaps() -> None:
    report = gap_report(_candidate(), _job())
    soft = [term for term in report.terms if term.kind == "soft"]

    assert len(soft) == 1
    assert soft[0].status is GapStatus.GAP
    assert report.missing == 1


def test_json_schema_is_stable() -> None:
    payload = gap_report(_candidate(), _job()).as_dict()

    assert set(payload) == {"job_id", "matched", "missing", "hard", "soft"}
    assert set(payload["hard"][0]) == {"term", "kind", "status", "span", "evidence"}
    assert payload["matched"] == 2
    assert payload["missing"] == 1


def test_command_writes_the_report_and_not_the_profile(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "data").mkdir()
    data = sample_profile_dict()
    data["skills"] = {"tools": ["postgres", "Excel"]}
    data["summary"] = "Coordina turnos."
    profile = tmp_path / "data" / "profile.yaml"
    profile.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    (tmp_path / ".jobbot.toml").write_text(
        f'[paths]\ntemplates = "{project_root / "templates"}"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    import jobbot.cli as cli
    from jobbot.cli import run_cli
    from jobbot.db.engine import make_engine, make_session_factory
    from jobbot.jobs.repository import JobRepository

    config = cli.load_config()
    session = make_session_factory(make_engine(config.database_path))()
    stored = JobRepository(session).upsert_external(_job())
    before = profile.read_bytes()
    description = JobRepository(session).get(stored.id).description

    code = run_cli(["cv", "gap", "--job", stored.id, "--json"], standalone_mode=False)

    assert code == SUCCESS
    assert profile.read_bytes() == before
    assert JobRepository(session).get(stored.id).description == description
    payload = json.loads(capsys.readouterr().out)
    assert payload["matched"] == 2
    assert payload["missing"] == 1
    cached = json.loads((tmp_path / "output" / "jobs" / stored.id / "gap.json").read_text())
    assert cached["job_id"] == stored.id
