"""Job CV trims skills, courses and old roles. The profile keeps every fact."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from jobbot.cv.pages import pages_from_xelatex_log, plan_page_trim
from jobbot.cv.renderer import render_cv_ats, render_cv_tex
from jobbot.cv.selection import select_for_base_cv, select_for_job
from jobbot.models.candidate import Candidate
from jobbot.models.education import Education
from jobbot.models.job import JobPosting
from tests.fixtures.profile import non_data_profile_dict


def _candidate() -> Candidate:
    data = non_data_profile_dict()
    data["skills"] = {
        "vigilancia": ["R", "QGIS"],
        "gestion": ["Coordinación interinstitucional"],
        "ofimatica": ["Excel"],
    }
    data["experience"] = [
        {
            "id": "old-role",
            "company": "Servicio Regional Ficticio",
            "title": "Analista",
            "location": "Chile",
            "start_date": "2010-01",
            "end_date": "2012-06",
            "current": False,
            "description": "Informes de vigilancia.",
            "achievements": [
                {"id": "old-ach", "text": "Informe anual de vigilancia.", "tags": []},
            ],
        }
    ]
    data["education"] = [
        {
            "id": "degree-1",
            "institution": "Universidad del Litoral",
            "degree": "Ingeniera",
            "kind": "degree",
            "start_date": "2000-03",
            "end_date": "2005-12",
        },
        {
            "id": "course-food",
            "institution": "Instituto Ficticio",
            "degree": "Curso de inocuidad",
            "kind": "course",
            "tags": ["inocuidad_alimentaria"],
            "start_date": "2018-01",
            "end_date": "2018-03",
        },
        {
            "id": "course-emerg",
            "institution": "Instituto Ficticio",
            "degree": "Curso de emergencias",
            "kind": "course",
            "tags": ["gestion_de_emergencias"],
            "start_date": "2019-01",
            "end_date": "2019-06",
        },
    ]
    return Candidate.model_validate(data)


def _job(*skills: str) -> JobPosting:
    return JobPosting(
        id="J0143",
        title="Aviso",
        company="Estudio Neutro",
        description="Una descripcion de un aviso. " * 20,
        skills=list(skills),
    )


def test_job_cv_keeps_only_skills_the_posting_names(project_root: Path) -> None:
    candidate = _candidate()
    templates = project_root / "templates"
    selection = select_for_job(
        candidate, _job("coordinación interinstitucional", "Excel")
    )
    job_tex = render_cv_tex(candidate, templates, selection)
    job_ats = render_cv_ats(candidate, templates, selection)
    base_tex = render_cv_tex(candidate, templates)
    base_ats = render_cv_ats(candidate, templates)

    for text in (job_tex, job_ats):
        assert "Coordinación interinstitucional" in text
        assert "Excel" in text
        assert "QGIS" not in text
    for text in (base_tex, base_ats):
        assert "QGIS" in text
        assert "Excel" in text
        assert "Coordinación interinstitucional" in text


def test_job_cv_keeps_degree_and_the_course_the_posting_names() -> None:
    candidate = _candidate()
    selection = select_for_job(candidate, _job("gestión de emergencias"))
    payload = selection.to_dict()

    assert payload["education_ids"] == ["degree-1", "course-emerg"]


def test_compact_before_drops_achievements_of_an_old_role(project_root: Path) -> None:
    candidate = _candidate()
    templates = project_root / "templates"
    selection = select_for_base_cv(candidate)
    compact_tex = render_cv_tex(candidate, templates, selection, compact_before="2014-01")
    compact_ats = render_cv_ats(candidate, templates, selection, compact_before="2014-01")
    full_tex = render_cv_tex(candidate, templates, selection)
    full_ats = render_cv_ats(candidate, templates, selection)

    assert "Analista" in compact_tex
    assert "Analista" in compact_ats
    assert "Informe anual de vigilancia" not in compact_tex
    assert "Informe anual de vigilancia" not in compact_ats
    assert "Informe anual de vigilancia" in full_tex
    assert "Informe anual de vigilancia" in full_ats


def test_xelatex_log_page_count_and_trim_order() -> None:
    log = "Output written on cv.pdf (3 pages, 123456 bytes).\n"
    assert pages_from_xelatex_log(log) == 3
    assert pages_from_xelatex_log("Output written on cv.pdf (1 page, 10 bytes).") == 1
    earlier = "Output written on cv.pdf (2 pages, 1 bytes).\n" + log
    assert pages_from_xelatex_log(earlier) == 3

    plan = plan_page_trim(
        pages=4,
        max_pages=2,
        finished=[("mid", "2016-01"), ("old", "2010-01")],
        course_ids=["c1"],
    )
    assert plan.compact_ids == ("old", "mid")
    assert plan.drop_course_ids == ("c1",)
    assert plan.warning is not None
    assert "4 pages exceeds max_pages 2" in plan.warning

    under = plan_page_trim(
        pages=2,
        max_pages=2,
        finished=[("old", "2010-01")],
        course_ids=["c1"],
    )
    assert under.compact_ids == ()
    assert under.drop_course_ids == ()
    assert under.warning is None


def test_unknown_education_kind_names_the_two_values() -> None:
    with pytest.raises(ValidationError, match="degree, course"):
        Education(id="x", institution="Instituto", degree="Curso", kind="seminar")
