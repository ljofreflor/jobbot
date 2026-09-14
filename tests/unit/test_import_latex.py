"""Tests for moderncv LaTeX importer."""

from __future__ import annotations

from pathlib import Path

from jobbot.models.candidate import Candidate
from jobbot.profile.importer_latex import import_latex_cv, write_generated_profile
from jobbot.profile.loader import load_profile
from jobbot.profile.validator import validate_candidate


def test_import_moderncv_fixture(project_root: Path, tmp_path: Path) -> None:
    tex = project_root / "tests" / "fixtures" / "moderncv_sample.tex"
    result = import_latex_cv(tex)

    assert result.data["personal"]["name"] == "Ana Ejemplo"
    assert "Senior Data Scientist" in result.data["personal"]["headline"]
    assert result.data["personal"]["email"] == "ana.ejemplo@example.com"
    assert result.data["personal"]["linkedin"].endswith("/ana-ejemplo")
    assert result.data["summary"]
    assert "causal inference" in result.data["summary"].lower()

    experiences = result.data["experience"]
    assert len(experiences) == 2
    thoughtworks = next(e for e in experiences if "Thoughtworks" in e["company"])
    assert thoughtworks["current"] is True
    assert thoughtworks["start_date"] == "2025-10"
    assert "end_date" not in thoughtworks or thoughtworks.get("end_date") is None

    meli = next(e for e in experiences if "Mercado Libre" in e["company"])
    assert meli["start_date"] == "2022-04"
    assert meli["end_date"] == "2025-05"
    assert len(meli["achievements"]) == 2
    assert any("Share of Wallet" in a["text"] for a in meli["achievements"])

    education = result.data["education"]
    assert len(education) == 2
    assert any("Magíster" in e["degree"] for e in education)

    skills = result.data["skills"]
    assert "Python" in skills["programming"]
    assert "XGBoost" in skills["machine_learning"]
    assert "GCP" in skills["cloud"]

    pubs = result.data["publications"]
    assert len(pubs) == 2
    assert pubs[0]["year"] == 2022
    assert pubs[0]["doi"] == "10.1038/s41598-022-13743-8"
    assert "doi" not in pubs[1]

    out = tmp_path / "profile.generated.yaml"
    write_generated_profile(result, out)
    candidate = load_profile(out)
    assert validate_candidate(candidate).ok
    assert isinstance(candidate, Candidate)


def test_parse_present_and_year_only_dates(project_root: Path) -> None:
    tex = project_root / "tests" / "fixtures" / "moderncv_sample.tex"
    result = import_latex_cv(tex)
    phd = next(e for e in result.data["education"] if "Doctorado" in e["degree"])
    assert phd["start_date"] == "2020-01"
    assert "end_date" not in phd
