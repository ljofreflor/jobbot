"""CV rendering tests (no XeLaTeX required)."""

from __future__ import annotations

from pathlib import Path

from jobbot.cv.build import BuildTarget, build_cv
from jobbot.cv.renderer import render_cv_ats, render_cv_tex
from jobbot.models.candidate import Candidate
from tests.fixtures.profile import sample_profile_dict


def test_render_tex_escapes_and_includes_name(project_root: Path) -> None:
    data = sample_profile_dict()
    data["personal"]["name"] = "Ana & Co"
    candidate = Candidate.model_validate(data)
    tex = render_cv_tex(candidate, project_root / "templates")
    # moderncv splits the name: \name{given}{family}, each escaped on its own
    assert r"\name{Ana}{\& Co}" in tex
    assert "Mercado Libre" in tex
    assert "Share of Wallet" in tex


def test_render_ats_plain_text(project_root: Path) -> None:
    candidate = Candidate.model_validate(sample_profile_dict())
    ats = render_cv_ats(candidate, project_root / "templates")
    assert "SUMMARY" in ats
    assert "EXPERIENCE" in ats
    assert "SKILLS" in ats
    assert "Ana Ejemplo" in ats
    assert "Python" in ats
    assert "\\section" not in ats
    assert "\\textbf" not in ats


def test_render_ats_keeps_every_field_on_its_own_line(project_root: Path) -> None:
    """Jinja trim_blocks drops the newline after a block tag: fields glued together."""
    data = sample_profile_dict()
    data["experience"][0]["achievements"].append(
        {
            "id": "meli-experimentation",
            "text": "Framework de experimentación A/B.",
            "tags": [],
            "metrics": {},
        }
    )
    data["experience"].append(
        {
            "id": "retail-co",
            "company": "Retail Co",
            "title": "Data Scientist",
            "location": "Santiago, Chile",
            "start_date": "2019-01",
            "end_date": "2022-03",
            "current": False,
            "description": "Forecasting y pricing para retail omnicanal.",
            "achievements": [],
        }
    )
    candidate = Candidate.model_validate(data)

    lines = render_cv_ats(candidate, project_root / "templates").splitlines()

    assert "2022-04 – 2025-05 | Remote" in lines
    assert "Customer analytics & credit risk." in lines
    assert "- Framework de experimentación A/B." in lines
    assert "Data Scientist — Retail Co" in lines
    assert "Forecasting y pricing para retail omnicanal." in lines
    assert "EDUCATION" in lines
    assert "SKILLS" in lines
    assert "PUBLICATIONS" in lines


def test_build_ats_writes_file(project_root: Path, tmp_path: Path) -> None:
    candidate = Candidate.model_validate(sample_profile_dict())
    outputs = build_cv(
        candidate=candidate,
        templates_dir=project_root / "templates",
        output_dir=tmp_path / "output",
        target=BuildTarget.ATS,
    )
    assert len(outputs) == 1
    assert outputs[0].name == "cv_ats.txt"
    assert outputs[0].is_file()
    assert "EXPERIENCE" in outputs[0].read_text(encoding="utf-8")


def test_split_name_spanish_two_given_two_family() -> None:
    from jobbot.cv.renderer import split_name

    assert split_name("Leonardo Andrés Jofré Flor") == ("Leonardo Andrés", "Jofré Flor")
    assert split_name("Ana Pérez Soto") == ("Ana", "Pérez Soto")
    assert split_name("Ana Ejemplo") == ("Ana", "Ejemplo")
    assert split_name("Ana") == ("Ana", "")


def test_social_handle_from_url() -> None:
    from jobbot.cv.renderer import social_handle

    assert social_handle("https://www.linkedin.com/in/leonardojofre") == "leonardojofre"
    assert social_handle("https://github.com/ljofreflor/") == "ljofreflor"
    assert social_handle("") is None


def test_render_moderncv_matches_the_real_cv_design(project_root: Path) -> None:
    """The derived CV must look like the candidate's own LaTeX CV (moderncv banking)."""
    from jobbot.cv.renderer import CvStyle

    candidate = Candidate.model_validate(sample_profile_dict())
    tex = render_cv_tex(candidate, project_root / "templates", style=CvStyle.MODERNCV)

    assert r"\documentclass[11pt,a4paper,sans]{moderncv}" in tex
    assert r"\moderncvstyle{banking}" in tex
    assert r"\setmainlanguage{spanish}" in tex
    assert r"\makecvtitle" in tex
    assert r"\cventry{" in tex
    assert r"\cvitem{" in tex
    assert r"\section{Resumen Profesional}" in tex
    assert r"\section{Experiencia Profesional}" in tex
    assert r"\section{Habilidades}" in tex
    assert "Mercado Libre" in tex
    # article-only markup must not leak into the moderncv build
    assert r"\documentclass[11pt,a4paper]{article}" not in tex
    assert r"\section*{Summary}" not in tex


def test_render_plain_style_still_available(project_root: Path) -> None:
    from jobbot.cv.renderer import CvStyle

    candidate = Candidate.model_validate(sample_profile_dict())
    tex = render_cv_tex(candidate, project_root / "templates", style=CvStyle.PLAIN)
    assert r"\documentclass[11pt,a4paper]{article}" in tex


def test_build_cv_moderncv_writes_tex_for_job(project_root: Path, tmp_path: Path) -> None:
    """Job builds go through the same style as the base CV."""
    from jobbot.cv.renderer import CvStyle, render_cv_tex

    candidate = Candidate.model_validate(sample_profile_dict())
    tex = render_cv_tex(candidate, project_root / "templates", style=CvStyle.MODERNCV)
    assert candidate.personal.headline is None or candidate.personal.headline in tex


def test_es_date_range_matches_the_real_cv_format() -> None:
    """The real CV writes 'Abr 2022 – May 2025 (3 años, 2 meses)'."""
    from jobbot.cv.renderer import es_date_range

    assert es_date_range("2022-04", "2025-05") == "Abr 2022 – May 2025 (3 años, 2 meses)"
    assert es_date_range("2025-10", None) == "Oct 2025 – Presente"
    assert es_date_range("2008-01", "2014-12") == "Ene 2008 – Dic 2014 (7 años)"
    assert es_date_range("2019-05", "2019-08") == "May 2019 – Ago 2019 (4 meses)"
    assert es_date_range(None, None) == ""


def test_moderncv_renders_address_and_spanish_dates(project_root: Path) -> None:
    from jobbot.cv.renderer import CvStyle

    data = sample_profile_dict()
    data["personal"]["city"] = "Santiago"
    data["personal"]["country"] = "Chile"
    candidate = Candidate.model_validate(data)
    tex = render_cv_tex(candidate, project_root / "templates", style=CvStyle.MODERNCV)

    assert r"\address{Santiago}{Chile}{}" in tex
    # ISO months must not reach the PDF
    assert "2022-04" not in tex
    assert "Abr 2022" in tex


def test_moderncv_education_puts_degree_before_institution(project_root: Path) -> None:
    from jobbot.cv.renderer import CvStyle

    candidate = Candidate.model_validate(sample_profile_dict())
    tex = render_cv_tex(candidate, project_root / "templates", style=CvStyle.MODERNCV)
    edu = candidate.education[0]
    marker = rf"\textbf{{{edu.degree}}}}}{{{edu.institution}}}"
    assert marker in tex
