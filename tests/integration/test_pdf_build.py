"""Optional PDF build when XeLaTeX is available."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from jobbot.cv.build import BuildTarget, build_cv
from jobbot.models.candidate import Candidate
from tests.fixtures.profile import sample_profile_dict

pytestmark = pytest.mark.integration


@pytest.mark.skipif(shutil.which("xelatex") is None, reason="xelatex not installed")
def test_build_pdf(project_root: Path, tmp_path: Path) -> None:
    candidate = Candidate.model_validate(sample_profile_dict())
    outputs = build_cv(
        candidate=candidate,
        templates_dir=project_root / "templates",
        output_dir=tmp_path / "output",
        target=BuildTarget.CV,
    )
    names = {p.name for p in outputs}
    assert "cv.tex" in names
    assert "cv.pdf" in names
    assert (tmp_path / "output" / "base" / "cv.pdf").is_file()
