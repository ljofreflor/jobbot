"""An internship must not score as a perfect fit for someone who already holds a higher level."""

from __future__ import annotations

from jobbot.jobs.normalization import normalize_skill
from jobbot.jobs.parsing import parse_job_text
from jobbot.matching.analyzer import RuleBasedJobAnalyzer
from jobbot.models.candidate import Candidate

_REQUIREMENTS = """Requisitos:
- archivo
- turnos
- atención de público
"""


def _job(extra: str) -> str:
    return (
        "Title: Analista de archivo\n"
        "Company: Servicio Neutro\n"
        f"{extra}\n"
        f"{_REQUIREMENTS}"
    )


def _candidate(title: str) -> Candidate:
    return Candidate.model_validate(
        {
            "personal": {
                "name": "Ana Ejemplo",
                "email": "ana@example.com",
                "headline": "Analista de archivo",
            },
            "experience": [
                {
                    "id": "e1",
                    "company": "Servicio Neutro",
                    "title": title,
                    "start_date": "2020-01",
                    "current": True,
                    "achievements": [
                        {
                            "id": "a1",
                            "text": "Archivo, registro de turnos y atención de público.",
                            "tags": ["archivo", "turnos"],
                        }
                    ],
                }
            ],
            "skills": {"other": ["archivo", "turnos", "atención de público"]},
        }
    )


def test_internship_wording_is_a_level_and_clinical_practice_is_not() -> None:
    assert parse_job_text(_job("modalidad de práctica"), job_id="J0701").seniority == "intern"
    assert parse_job_text(_job("práctica profesional"), job_id="J0702").seniority == "intern"
    assert parse_job_text(_job("Buscamos un pasante."), job_id="J0703").seniority == "intern"
    assert parse_job_text(_job("buenas prácticas de archivo"), job_id="J0704").seniority is None
    assert parse_job_text(_job("práctica clínica diaria"), job_id="J0705").seniority is None


def test_senior_profile_cannot_score_a_perfect_internship() -> None:
    candidate = _candidate("Analista senior de archivo")
    intern = parse_job_text(_job("modalidad de práctica"), job_id="J0706")
    staff = parse_job_text(_job("jornada completa"), job_id="J0707")

    intern_score = RuleBasedJobAnalyzer().analyze(candidate, intern).score
    staff_score = RuleBasedJobAnalyzer().analyze(candidate, staff).score

    assert staff_score > 40
    assert intern_score <= 40
    assert intern_score < staff_score


def test_an_interns_own_title_is_not_capped() -> None:
    candidate = _candidate("Analista pasante de archivo")
    job = parse_job_text(_job("modalidad de práctica"), job_id="J0708")

    assert RuleBasedJobAnalyzer().analyze(candidate, job).score > 40


def test_skill_aliases_stay_exact_and_unknown_terms_fall_through() -> None:
    assert normalize_skill("sklearn") == normalize_skill("scikit-learn") == "scikit_learn"
    assert normalize_skill("machine learning") == normalize_skill("ml") == "machine_learning"
    assert normalize_skill("archivo clínico") == "archivo_clinico"
