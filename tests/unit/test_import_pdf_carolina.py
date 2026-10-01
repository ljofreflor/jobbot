"""Regression: Carolina Baeza PDF fixture imports a named profile."""

from __future__ import annotations

from pathlib import Path

from jobbot.profile.importer_pdf import import_pdf_cv

_FIXTURE = Path("tests/fixtures/cvs/carolina_baeza/CV_Carolina_Baeza_2026.pdf")


def test_carolina_baeza_pdf_imports_name() -> None:
    assert _FIXTURE.is_file()
    result = import_pdf_cv(_FIXTURE)
    name = str(result.data.get("personal", {}).get("name") or "")
    assert "carolina" in name.casefold()
    assert "baeza" in name.casefold()
    assert result.experience_count >= 1
