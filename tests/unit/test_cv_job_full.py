"""`cv build --job --full`: every profile fact stays, ordered by the posting inside each role."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from jobbot.cv import build as build_module
from jobbot.cv.build import BuildTarget, build_cv
from jobbot.cv.latex import escape_latex
from jobbot.cv.renderer import CvStyle, render_cv_ats, render_cv_tex
from jobbot.cv.selection import filter_experiences, select_for_job
from jobbot.jobs.parsing import parse_job_text
from jobbot.models.candidate import Candidate
from jobbot.models.job import JobPosting


def _role(i: int, achievements: list[tuple[str, str]]) -> dict[str, Any]:
    return {
        "id": f"role-{i}",
        "company": f"Empresa Ejemplo {i}",
        "title": f"Cargo {i}",
        "location": "Santiago, Chile",
        "start_date": f"{2024 - i}-01",
        "end_date": f"{2024 - i}-12",
        "current": False,
        "description": f"Área de trabajo número {i}.",
        "achievements": [
            {"id": ach_id, "text": text, "tags": [], "metrics": {}} for ach_id, text in achievements
        ],
    }


def _profile() -> Candidate:
    """Six roles: the posting names tools in four of them, never in the first bullet."""
    experience = [
        _role(
            i,
            [
                (f"r{i}-plain", f"Coordiné la agenda semanal del área {i}."),
                (f"r{i}-tool", f"Modelo en Python y SQL para la red del sector {i}."),
            ],
        )
        for i in range(1, 5)
    ]
    experience[0]["achievements"].append(
        {"id": "r1-kriging", "text": "Mapa de presiones con Kriging.", "tags": [], "metrics": {}}
    )
    experience.append(_role(5, [("r5-plain", "Ordené el archivo de planos.")]))
    experience.append(_role(6, []))
    return Candidate.model_validate(
        {
            "personal": {"name": "Ana Ejemplo", "headline": "Analista", "email": "ana@example.com"},
            "summary": "Analista con experiencia en redes de servicio.",
            "specialties": ["Redes de distribución"],
            "experience": experience,
            "education": [
                {
                    "id": "edu-1",
                    "institution": "Universidad del Litoral",
                    "degree": "Ingeniería Civil",
                    "start_date": "2010-03",
                    "end_date": "2015-12",
                }
            ],
            "skills": {"programming": ["Python", "SQL"], "other": ["Kriging", "Cartografía"]},
            "publications": [
                {"id": "pub-1", "title": "Pérdidas en redes", "journal": "Revista de Ejemplo"}
            ],
            "projects": [
                {"id": "p-1", "name": "Huerto Comunitario", "description": "Huerto vecinal."}
            ],
        }
    )


def _job(project_root: Path) -> JobPosting:
    text = (project_root / "tests/fixtures/jobs/hydro_analyst_full.txt").read_text(encoding="utf-8")
    return parse_job_text(text, job_id="J0101")


def _facts(candidate: Candidate) -> list[str]:
    facts = [candidate.personal.headline, candidate.summary or "", *candidate.specialties]
    for exp in candidate.experience:
        facts += [exp.title, exp.company, exp.location or "", exp.description or ""]
        facts += [ach.text for ach in exp.achievements]
    for edu in candidate.education:
        facts += [edu.degree, edu.institution]
    facts += candidate.skills.all_skills()
    facts += [pub.title for pub in candidate.publications]
    facts += [project.name for project in candidate.projects]
    return [fact for fact in facts if fact]


def test_default_job_selection_still_trims(project_root: Path) -> None:
    candidate = _profile()
    selection = select_for_job(candidate, _job(project_root))

    kept = {ach.id for _, achs in filter_experiences(candidate, selection) for ach in achs}
    assert "r1-plain" not in kept
    assert "role-6" not in selection.experience_ids
    assert not selection.full


def test_full_job_selection_keeps_every_role_and_achievement(project_root: Path) -> None:
    candidate = _profile()
    selection = select_for_job(candidate, _job(project_root), full=True)

    rendered = filter_experiences(candidate, selection)
    assert [exp.id for exp, _ in rendered] == [exp.id for exp in candidate.experience]
    for (exp, achs), original in zip(rendered, candidate.experience, strict=True):
        assert sorted(a.id for a in achs) == sorted(a.id for a in original.achievements), exp.id
    assert selection.skill_names == candidate.skills.all_skills()


def test_full_job_selection_puts_related_achievements_first_inside_each_role(
    project_root: Path,
) -> None:
    candidate = _profile()
    selection = select_for_job(candidate, _job(project_root), full=True)

    order = {exp.id: [a.id for a in achs] for exp, achs in filter_experiences(candidate, selection)}
    assert order["role-1"][-1] == "r1-plain"
    assert set(order["role-1"][:2]) == {"r1-tool", "r1-kriging"}
    assert order["role-2"] == ["r2-tool", "r2-plain"]
    assert order["role-5"] == ["r5-plain"]
    unrelated = next(a for a in selection.selected_achievements if a.id == "r5-plain")
    assert unrelated.reason


@pytest.mark.parametrize("style", list(CvStyle))
def test_full_job_tex_and_ats_render_every_fact_in_the_same_order(
    project_root: Path, style: CvStyle
) -> None:
    candidate = _profile()
    selection = select_for_job(candidate, _job(project_root), full=True)
    tex = render_cv_tex(candidate, project_root / "templates", selection, style=style)
    ats = render_cv_ats(candidate, project_root / "templates", selection)

    assert [f for f in _facts(candidate) if escape_latex(f) not in tex] == []
    assert [f for f in _facts(candidate) if f not in ats] == []
    for text in (tex, ats):
        assert text.index("Modelo en Python y SQL para la red del sector 2") < text.index(
            "Coordiné la agenda semanal del área 2"
        )


def test_cli_full_without_job_is_a_usage_error() -> None:
    from typer.testing import CliRunner

    from jobbot.cli import app

    result = CliRunner().invoke(app, ["cv", "build", "--full"])

    assert result.exit_code == 2
    assert "--job" in result.output


def test_build_cv_full_writes_the_full_selection(
    project_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fake_pdf(tex_path: Path, work_dir: Path) -> Path:
        pdf = work_dir / "cv.pdf"
        pdf.write_bytes(b"%PDF-1.5\n")
        return pdf

    monkeypatch.setattr(build_module, "_compile_xelatex", fake_pdf)
    candidate = _profile()
    output = tmp_path / "output"
    build_cv(
        candidate,
        project_root / "templates",
        output,
        target=BuildTarget.CV,
        job=_job(project_root),
        full=True,
    )

    job_dir = output / "jobs" / "J0101"
    payload = json.loads((job_dir / "selection.json").read_text(encoding="utf-8"))
    assert payload["full"] is True
    ats = (job_dir / "cv_ats.txt").read_text(encoding="utf-8")
    assert [f for f in _facts(candidate) if f not in ats] == []
