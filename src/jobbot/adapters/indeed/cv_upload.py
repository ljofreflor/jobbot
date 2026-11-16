"""Decide whether an Indeed PDF upload is needed. The portal write stays HITL."""

from __future__ import annotations

import hashlib
import unicodedata
from pathlib import Path

import yaml

ALREADY_CURRENT = "CV ya vigente"
ICON_GLYPHS = "la capa de texto tiene glyphs de íconos"
KNOWN_VARIANTS = frozenset({"base_es", "base_en"})


def receipt_path(output_dir: Path) -> Path:
    return output_dir / "indeed" / "cv_receipt.yaml"


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_receipt_sha(output_dir: Path) -> str | None:
    path = receipt_path(output_dir)
    if not path.is_file():
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return None
    if not isinstance(data, dict):
        return None
    digest = data.get("sha256")
    return digest if isinstance(digest, str) and digest else None


def icon_glyph_message(path: Path) -> str | None:
    """Refuse a text layer whose characters are icon glyphs, not words."""
    from pypdf import PdfReader

    try:
        text = "\n".join(page.extract_text() or "" for page in PdfReader(str(path)).pages)
    except Exception as exc:  # noqa: BLE001 — a PDF we cannot read is not uploadable
        return f"no se pudo leer la capa de texto: {exc.__class__.__name__}"
    private = sum(1 for char in text if unicodedata.category(char) == "Co")
    letters = sum(
        1 for char in text if char.isalpha() and unicodedata.category(char) != "Co"
    )
    if private >= 3 and private >= letters:
        return ICON_GLYPHS
    return None
