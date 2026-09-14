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
    assert r"Ana \& Co" in tex
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
