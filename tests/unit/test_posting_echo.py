"""A prose posting with no extracted skills still selects by what it repeats."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from jobbot.cv.selection import select_for_job
from jobbot.exit_codes import SUCCESS
from jobbot.jobs.parsing import parse_job_text
from jobbot.models.candidate import Candidate
from jobbot.models.job import JobPosting
from jobbot.models.match import JobMatch, MatchItem, MatchStrength
from tests.fixtures.profile import sample_profile_dict

A_TEXT = "Coordinacion de una red nacional de laboratorios regionales"
C_TEXT = "Articulacion permanente con autoridades sanitarias regionales"
B_TEXT = "Atencion clinica de pacientes durante el turno hospitalario"
_PAD = " relleno" * 80


def _role(role_id: str, start: str, ach_id: str, text: str, tags: list[str]) -> dict[str, object]:
    return {
        "id": role_id,
        "company": "Organismo Ficticio",
        "title": "Cargo",
        "start_date": start,
        "end_date": "2024-12",
        "current": False,
        "achievements": [{"id": ach_id, "text": text, "tags": tags}],
    }


def _profile() -> Candidate:
    return Candidate.model_validate(
        {
            "personal": {
                "name": "Ana Ejemplo",
                "headline": "Profesional",
                "email": "ana@example.com",
            },
            "experience": [
                _role("role-a", "2020-01", "ach-a", A_TEXT, ["gestion_de_redes"]),
                _role("role-c", "2018-01", "ach-c", C_TEXT, []),
                _role("role-b", "2024-01", "ach-b", B_TEXT, []),
            ],
            "skills": {"other": ["Archivo"]},
        }
    )


def _posting(job_id: str, description: str) -> JobPosting:
    return JobPosting(
        id=job_id,
        title="Aviso",
        company="Organismo Ficticio",
        description=description,
        skills=[],
        requirements=[],
    )


def _reasons(selection: object, ach_id: str) -> list[str]:
    item = next(row for row in selection.selected_achievements if row.id == ach_id)  # type: ignore[attr-defined]
    return item.reason


def test_two_prose_postings_select_different_achievements() -> None:
    candidate = _profile()
    labs = _posting("J0101", f"Se pide {A_TEXT}.{_PAD}")
    authorities = _posting("J0102", f"Se pide {C_TEXT}.{_PAD}")

    first = select_for_job(candidate, labs)
    second = select_for_job(candidate, authorities)

    assert [row.id for row in first.selected_achievements] != [
        row.id for row in second.selected_achievements
    ]
    assert any(reason.startswith("posting echoes:") for reason in _reasons(first, "ach-a"))
    assert _reasons(first, "ach-b") == ["floor: few experiences matched the posting"]
    assert first.selected_achievements[-1].id == "ach-b"
    assert any(reason.startswith("posting echoes:") for reason in _reasons(second, "ach-c"))
    assert second.selected_achievements[-1].id == "ach-b"


def test_floor_reason_follows_the_posting_length() -> None:
    data = _profile().model_dump(mode="json")
    data["experience"].append(
        _role("role-d", "2016-01", "ach-d", "Inventario anual de estanterias", [])
    )
    candidate = Candidate.model_validate(data)
    long = _posting("J0103", "convocatoria abierta " * 400)
    short = _posting("J0104", "x" * 300)

    long_picked = select_for_job(candidate, long)
    long_reasons = " ".join(r for row in long_picked.selected_achievements for r in row.reason)
    short_reasons = " ".join(
        r for row in select_for_job(candidate, short).selected_achievements for r in row.reason
    )

    assert "short JD" not in long_reasons
    assert "few experiences matched" in long_reasons
    assert "short JD" in short_reasons


def test_no_echo_falls_back_to_recency() -> None:
    candidate = _profile()
    job = _posting("J0105", "convocatoria abierta " * 30)
    selection = select_for_job(candidate, job)
    assert selection.experience_ids[0] == "role-b"
    assert selection.selected_achievements[0].id == "ach-b"
    assert selection.selected_achievements[0].reason == [
        "fallback: no strong keyword overlap; kept recent evidence"
    ]
    assert not selection.used_posting_terms


def test_a_match_echo_is_reused_when_the_posting_has_no_terms() -> None:
    candidate = _profile()
    job = _posting("J0106", "convocatoria abierta " * 30)
    match = JobMatch(
        job_id=job.id,
        score=10,
        items=[
            MatchItem(
                label="achievement:ach-a",
                strength=MatchStrength.STRONG,
                detail="the posting echoes: laboratorios, regionales",
            )
        ],
    )
    selection = select_for_job(candidate, job, match)
    assert _reasons(selection, "ach-a") == ["posting echoes: laboratorios, regionales"]


def test_extracted_skills_keep_the_token_selection(project_root: Path) -> None:
    candidate = Candidate.model_validate(sample_profile_dict())
    job = parse_job_text(
        (project_root / "tests/fixtures/jobs/senior_ds_retail.txt").read_text(encoding="utf-8"),
        job_id="J0001",
    )
    assert len(job.skills) >= 3
    selection = select_for_job(candidate, job)
    reasons = " ".join(r for row in selection.selected_achievements for r in row.reason)
    assert "posting echoes:" not in reasons
    assert "meli-share-of-wallet" in {row.id for row in selection.selected_achievements}
    assert selection.used_posting_terms


def test_cv_build_warns_when_the_posting_has_no_terms(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    data = {
        "personal": {
            "name": "Ana Ejemplo",
            "headline": "Profesional",
            "email": "ana@example.com",
        },
        "experience": [
            _role("role-old", "2010-01", "ach-old", "Archivo de expedientes internos", []),
            _role("role-new", "2024-01", "ach-new", "Custodia de bodegas municipales", []),
        ],
        "skills": {"other": ["Archivo"]},
    }
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "profile.yaml").write_text(
        yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    (tmp_path / ".jobbot.toml").write_text(
        f'[paths]\ntemplates = "{project_root / "templates"}"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    from jobbot.cli import load_config, run_cli
    from jobbot.db.engine import make_engine, make_session_factory
    from jobbot.jobs.repository import JobRepository

    config = load_config()
    session = make_session_factory(make_engine(config.database_path))()
    JobRepository(session).save(_posting("J0001", "convocatoria abierta " * 30))

    code = run_cli(["cv", "build", "--target", "ats", "--job", "J0001"], standalone_mode=False)
    assert code == SUCCESS
    assert (
        "selección sin términos del aviso; revisa selection.json o re-parsea el aviso"
        in capsys.readouterr().err
    )
