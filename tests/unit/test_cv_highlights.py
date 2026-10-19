"""Highlights copy quantified bullets. A posting only breaks ties."""

from __future__ import annotations

from pathlib import Path

from jobbot.cv.highlights import select_highlights
from jobbot.cv.renderer import render_cv_tex
from jobbot.models.candidate import Candidate
from jobbot.models.job import JobPosting
from tests.fixtures.profile import sample_profile_dict

_HOURS = "Reduje el tiempo de entrega en 12 horas."
_SHIFTS = "Cubri 40 turnos de noche en un trimestre."
_ONLY_JD = "Ventilacion mecanica"


def _candidate() -> Candidate:
    data = sample_profile_dict()
    data["experience"] = [
        {
            "id": "role",
            "company": "Servicio Neutro",
            "title": "Analista",
            "start_date": "2020-01",
            "current": True,
            "achievements": [
                {"id": "a1", "text": "Coordiné la entrega de turno entre equipos."},
                {"id": "a2", "text": _HOURS},
                {"id": "a3", "text": "Mantuve el registro clínico al día."},
                {"id": "a4", "text": _SHIFTS},
                {"id": "a5", "text": "Organicé la inducción del personal nuevo."},
            ],
        }
    ]
    return Candidate.model_validate(data)


def _job() -> JobPosting:
    return JobPosting(
        id="J0001",
        title="Cobertura de turnos",
        company="Servicio Neutro",
        description=f"Se necesitan turnos de noche. {_ONLY_JD} no está en el perfil.",
    )


def test_quantified_bullets_stay_in_profile_order() -> None:
    plan = select_highlights(_candidate())

    assert plan.lines == (_HOURS, _SHIFTS)
    assert plan.warning == ""


def test_job_overlap_breaks_ties_without_copying_job_only_words() -> None:
    plan = select_highlights(_candidate(), _job())

    assert plan.lines == (_SHIFTS, _HOURS)
    assert _ONLY_JD.casefold() not in " ".join(plan.lines).casefold()
    assert plan.lines[0] == _SHIFTS


def test_no_quantified_bullet_warns_and_adds_nothing() -> None:
    data = sample_profile_dict()
    data["experience"] = [
        {
            "id": "role",
            "company": "Servicio Neutro",
            "title": "Analista",
            "start_date": "2020-01",
            "current": True,
            "achievements": [{"id": "a1", "text": "Coordiné la entrega de turno entre equipos."}],
        }
    ]
    plan = select_highlights(Candidate.model_validate(data))

    assert plan.lines == ()
    assert "no quantified bullet" in plan.warning


def test_highlights_section_is_absent_unless_requested(project_root: Path) -> None:
    candidate = _candidate()
    plain = render_cv_tex(candidate, project_root / "templates")
    shown = render_cv_tex(
        candidate,
        project_root / "templates",
        highlights=select_highlights(candidate).lines,
    )

    assert r"\section{Logros}" not in plain
    assert r"\section{Logros}" in shown
    assert _HOURS in shown
    assert _SHIFTS in shown
    assert shown.index(_HOURS) < shown.index(_SHIFTS)
