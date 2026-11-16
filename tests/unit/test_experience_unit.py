"""An experience can name its unit and work mode without changing older CVs."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from jobbot.companies.signup import signup_sheet
from jobbot.cv.renderer import CvStyle, render_cv_ats, render_cv_tex
from jobbot.models.candidate import Candidate
from jobbot.models.experience import Experience
from jobbot.portals.form_learn import FieldKind, FormField, FormKnowledge
from tests.fixtures.profile import sample_profile_dict

_ATS_LINE = (
    "Analista — Servicio Regional Ficticio · "
    "Unidad de Vigilancia Epidemiológica | Chile (remoto)"
)


def _candidate(**role: object) -> Candidate:
    experience: dict[str, object] = {
        "id": "analista-vigilancia",
        "company": "Servicio Regional Ficticio",
        "unit": "Unidad de Vigilancia Epidemiológica",
        "title": "Analista",
        "location": "Chile",
        "work_mode": "remote",
        "start_date": "2020-01",
        "end_date": "2024-06",
        "current": False,
        "achievements": [],
    }
    experience.update(role)
    return Candidate.model_validate(
        {
            "personal": {
                "name": "Ana Ejemplo",
                "headline": "Analista",
                "email": "ana.ejemplo@example.com",
            },
            "summary": (
                "Trabajo en la unidad de un servicio regional, con terreno y con oficina."
            ),
            "experience": [experience],
        }
    )


def test_moderncv_splits_employer_and_unit(project_root: Path) -> None:
    tex = render_cv_tex(_candidate(), project_root / "templates", style=CvStyle.MODERNCV)
    assert "Servicio Regional Ficticio" in tex
    assert "Unidad de Vigilancia Epidemiológica" in tex
    assert "Chile · Remoto" in tex
    assert "Servicio Regional Ficticio Unidad de Vigilancia" not in tex


def test_ats_line_names_unit_and_mode(project_root: Path) -> None:
    ats = render_cv_ats(_candidate(), project_root / "templates")
    assert _ATS_LINE in ats


def test_ats_line_follows_the_english_headings_when_the_profile_is_too_short(
    project_root: Path,
) -> None:
    candidate = _candidate().model_copy(update={"summary": "Epidemiology analyst."})
    ats = render_cv_ats(candidate, project_root / "templates")
    assert "| Chile (remote)" in ats
    assert "(remoto)" not in ats


def test_the_name_is_not_evidence_of_the_profile_language(project_root: Path) -> None:
    personal = _candidate().personal.model_copy(update={"name": "Ana de la Fuente Rivas"})
    candidate = _candidate().model_copy(
        update={
            "personal": personal,
            "summary": "Analyst of the surveillance data in the regional service.",
        }
    )
    ats = render_cv_ats(candidate, project_root / "templates")
    assert "| Chile (remote)" in ats


def test_signup_employer_is_the_company_without_the_unit() -> None:
    form = FormKnowledge(
        url="https://example.test/jobs",
        readable=True,
        fields=[
            FormField(name="employer", label="Employer", kind=FieldKind.TEXT),
            FormField(name="unit", label="Department", kind=FieldKind.TEXT),
        ],
    )
    sheet = {item.label: item for item in signup_sheet(_candidate(), form=form)}
    assert sheet["Employer"].value == "Servicio Regional Ficticio"
    assert "Unidad" not in sheet["Employer"].value
    assert sheet["Department"].value == "Unidad de Vigilancia Epidemiológica"


def test_signup_employer_is_the_role_that_ended_last() -> None:
    long_job = {
        "id": "analista-larga",
        "company": "Servicio Regional Ficticio",
        "title": "Analista",
        "start_date": "2018-01",
        "end_date": "2024-06",
        "current": False,
        "achievements": [],
    }
    short_contract = {
        "id": "asesoria-breve",
        "company": "Consultora Ficticia",
        "title": "Asesor",
        "start_date": "2020-01",
        "end_date": "2020-06",
        "current": False,
        "achievements": [],
    }
    roles = [Experience.model_validate(role) for role in (long_job, short_contract)]
    candidate = _candidate().model_copy(update={"experience": roles})
    form = FormKnowledge(
        url="https://example.test/jobs",
        readable=True,
        fields=[FormField(name="employer", label="Employer", kind=FieldKind.TEXT)],
    )
    sheet = {item.label: item for item in signup_sheet(candidate, form=form)}
    assert sheet["Employer"].value == "Servicio Regional Ficticio"


def test_unknown_work_mode_lists_the_valid_values() -> None:
    with pytest.raises(ValidationError) as exc:
        _candidate(work_mode="teletrabajo")
    message = str(exc.value)
    assert "remote" in message
    assert "onsite" in message
    assert "hybrid" in message


def test_profile_without_unit_or_mode_renders_as_before(project_root: Path) -> None:
    candidate = Candidate.model_validate(sample_profile_dict())
    templates = project_root / "templates"
    ats = render_cv_ats(candidate, templates)
    tex = render_cv_tex(candidate, templates, style=CvStyle.MODERNCV)
    assert "Senior Data Scientist — Mercado Libre" in ats
    assert "2022-04 – 2025-05 | Remote" in ats
    assert "Mercado Libre ·" not in tex
    assert "· Remoto" not in tex
    assert "· Remote" not in tex
