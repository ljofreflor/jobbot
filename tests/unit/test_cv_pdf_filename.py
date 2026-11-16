"""Person-named CV PDF next to the stable cv.pdf artifact."""

from __future__ import annotations

from pathlib import Path

from jobbot.cv.build import cv_pdf_person_stem, write_named_cv_pdf


def test_cv_pdf_person_stem_strips_accents_and_joins_with_underscores() -> None:
    assert cv_pdf_person_stem("Leonardo Andrés Jofré Flor") == "Leonardo_Andres_Jofre_Flor"
    assert cv_pdf_person_stem("  Ana  Ejemplo  ") == "Ana_Ejemplo"
    assert cv_pdf_person_stem("Marta Soto Vera") == "Marta_Soto_Vera"


def test_cv_pdf_person_stem_drops_path_hostile_characters() -> None:
    assert cv_pdf_person_stem("Ada/Lovelace") == "Ada_Lovelace"
    assert cv_pdf_person_stem("Jean-Luc Picard") == "Jean_Luc_Picard"
    assert cv_pdf_person_stem("???") == "cv"
    assert cv_pdf_person_stem("") == "cv"


def test_write_named_cv_pdf_copies_beside_stable_artifact(tmp_path: Path) -> None:
    stable = tmp_path / "cv.pdf"
    stable.write_bytes(b"%PDF-1.4 person-named")
    named = write_named_cv_pdf(stable, "Leonardo Andrés Jofré Flor")
    assert named == tmp_path / "Leonardo_Andres_Jofre_Flor_CV.pdf"
    assert named.is_file()
    assert named.read_bytes() == stable.read_bytes()
    assert stable.is_file()


def test_write_named_cv_pdf_keeps_stable_when_name_is_cv(tmp_path: Path) -> None:
    """Stem fallback 'cv' still uses the _CV suffix, so it never replaces cv.pdf."""
    stable = tmp_path / "cv.pdf"
    stable.write_bytes(b"%PDF-1.4")
    named = write_named_cv_pdf(stable, "cv")
    assert named == tmp_path / "Cv_CV.pdf"
    assert named.read_bytes() == b"%PDF-1.4"
    assert stable.read_bytes() == b"%PDF-1.4"
