"""Public-contest admissibility is the posting's own rules, offline (#280)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import yaml

from jobbot.exit_codes import SUCCESS, VALIDATION_FAILURE
from jobbot.jobs.admissibility import assess, contest_code, extract_rules, shortlist_mark
from jobbot.models.candidate import Candidate

FIXTURES = Path(__file__).parents[1] / "fixtures" / "admissibility"
TODAY = date(2026, 10, 18)


def _candidate(
    *,
    degree: str = "Periodista",
    semesters: int | None = None,
    leadership: bool | None = None,
    start: str = "2019-10",
    end: str = "2026-10",
) -> Candidate:
    return Candidate.model_validate(
        {
            "personal": {"name": "Ana Ejemplo", "headline": "Profesional"},
            "education": [
                {
                    "id": "edu1",
                    "institution": "Universidad Ejemplo",
                    "degree": degree,
                    "duration_semesters": semesters,
                }
            ],
            "experience": [
                {
                    "id": "exp1",
                    "company": "Organismo Ejemplo",
                    "title": "Profesional",
                    "start_date": start,
                    "end_date": end,
                    "leadership": leadership,
                }
            ],
        }
    )


def test_closed_degree_list_rejects_a_different_title() -> None:
    text = (FIXTURES / "ep_lista_cerrada.html").read_text(encoding="utf-8")

    verdict = assess(extract_rules(text), _candidate(), contest_code=contest_code(text, "J1"))

    assert verdict.status == "no_admisible"
    assert "Enfermera" in verdict.rule
    assert "Estadístico" in verdict.rule


def test_open_area_asks_with_the_profile_title_and_the_contest_code() -> None:
    text = (FIXTURES / "ep_area_abierta.html").read_text(encoding="utf-8")

    verdict = assess(
        extract_rules(text),
        _candidate(degree="Periodista", semesters=10),
        contest_code=contest_code(text, "J1"),
    )

    assert verdict.status == "dudoso"
    assert verdict.question is not None
    assert "Periodista" in verdict.question
    assert "10 semestres" in verdict.question
    assert "Ciencias de la Salud" in verdict.question
    assert "CONC-0002" in verdict.question


def test_semester_alternative_uses_the_first_group_when_both_fit() -> None:
    text = (FIXTURES / "ep_semestres_alternativas.html").read_text(encoding="utf-8")
    rules = extract_rules(text)

    verdict = assess(rules, _candidate(semesters=10), today=TODAY)

    assert verdict.status == "admisible"
    assert "10 semestres" in verdict.rule
    assert {rule.alternatives_group for rule in rules} == {0, 1}


def test_missing_semesters_stay_a_question() -> None:
    text = (FIXTURES / "ep_semestres_alternativas.html").read_text(encoding="utf-8")

    verdict = assess(rules := extract_rules(text), _candidate(), today=TODAY)

    assert rules
    assert verdict.status == "dudoso"
    assert verdict.question is not None
    assert "semestres" in verdict.question


def test_leadership_is_doubtful_until_every_role_says_no() -> None:
    text = (FIXTURES / "adp_jefatura.html").read_text(encoding="utf-8")
    rules = extract_rules(text)

    unknown = assess(rules, _candidate(leadership=None), today=TODAY)
    denied = assess(rules, _candidate(leadership=False), today=TODAY)

    assert unknown.status == "dudoso"
    assert unknown.question is not None
    assert "jefatura" in unknown.question
    assert denied.status == "no_admisible"


def test_function_profile_and_competency_table_add_no_rule() -> None:
    text = (FIXTURES / "ep_perfil_funcion_competencias.html").read_text(encoding="utf-8")

    rules = extract_rules(text)

    blob = " ".join(rule.source_text for rule in rules).casefold()
    assert rules
    assert "periodista" in blob
    assert "rango" not in blob
    assert "ingeniero" not in blob


def test_sheet_without_an_exclusive_block_is_doubtful() -> None:
    verdict = assess(extract_rules("<p>Perfil de la Función</p>"), _candidate())

    assert verdict.status == "dudoso"
    assert verdict.evidence == "ficha sin requisitos excluyentes legibles"


def test_extractor_holds_no_profession_list() -> None:
    source = Path("src/jobbot/jobs/admissibility.py").read_text(encoding="utf-8").casefold()

    for word in ("enfermer", "estadistic", "periodis", "ingenier"):
        assert word not in source


def test_shortlist_mark_reads_only_a_stored_verdict(tmp_path: Path) -> None:
    path = tmp_path / "admissibility.json"
    assert shortlist_mark(path) == ""
    path.write_text('{"status": "no_admisible"}\n', encoding="utf-8")
    assert shortlist_mark(path) == "  [no admisible]"
    path.write_text('{"status": "admisible"}\n', encoding="utf-8")
    assert shortlist_mark(path) == ""


def test_cli_marks_the_shortlist_and_keeps_the_posting(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    data = tmp_path / "data"
    data.mkdir()
    (tmp_path / "output").mkdir()
    example = project_root / "data" / "profile.example.yaml"
    raw = yaml.safe_load(example.read_text(encoding="utf-8"))
    (data / "profile.yaml").write_text(
        yaml.safe_dump(raw, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    (tmp_path / ".jobbot.toml").write_text(
        f'[paths]\ntemplates = "{project_root / "templates"}"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    from jobbot.cli import run_cli
    from jobbot.config import load_config
    from jobbot.db.engine import make_engine, make_session_factory
    from jobbot.jobs.repository import JobRepository
    from jobbot.models.job import JobPosting

    config = load_config()
    session = make_session_factory(make_engine(config.database_path))()
    JobRepository(session).save(
        JobPosting(
            id="J0001",
            source="empleos_publicos",
            title="Concurso de ejemplo",
            company="Organismo Ejemplo",
            url="https://empleos.example.org/conc-0001",
            raw_description=(FIXTURES / "ep_lista_cerrada.html").read_text(encoding="utf-8"),
        )
    )
    session.commit()

    code = run_cli(["jobs", "admissibility", "J0001"], standalone_mode=False)
    out = capsys.readouterr().out
    assert code == SUCCESS
    assert "no_admisible" in out
    stored = tmp_path / "output" / "jobs" / "J0001" / "admissibility.json"
    assert stored.is_file()
    assert "no_admisible" in stored.read_text(encoding="utf-8")

    listed = run_cli(["jobs", "shortlist"], standalone_mode=False)
    shortlist = capsys.readouterr().out
    assert listed == SUCCESS
    assert "Concurso de ejemplo" in shortlist
    assert "[no admisible]" in shortlist

    missing = run_cli(["jobs", "admissibility", "J9999"], standalone_mode=False)
    captured = capsys.readouterr()
    assert missing == VALIDATION_FAILURE
    assert "J9999" in captured.err
