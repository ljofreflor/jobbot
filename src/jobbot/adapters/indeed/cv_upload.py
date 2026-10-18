"""Decide whether an Indeed PDF upload is needed. The portal write stays HITL."""

from __future__ import annotations

import hashlib
import unicodedata
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from jobbot.adapters.indeed.selectors import INDEED_RESUME

if TYPE_CHECKING:
    from playwright.sync_api import Page

ALREADY_CURRENT = "CV ya vigente"
ICON_GLYPHS = "la capa de texto tiene glyphs de íconos"
KNOWN_VARIANTS = frozenset({"base_es", "base_en"})
FILE_INPUT = 'input[type="file"]'
NO_FILE_CONTROL = f"no hay control de archivo en {INDEED_RESUME}"


class IndeedCvUploadError(RuntimeError):
    """The Indeed CV page did not offer the control this upload needs."""


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


def write_receipt(output_dir: Path, path: Path, *, sha256: str, variant: str) -> Path:
    """Record the attached PDF so the next run sees the same hash and does nothing."""
    receipt = receipt_path(output_dir)
    receipt.parent.mkdir(parents=True, exist_ok=True)
    receipt.write_text(
        yaml.safe_dump(
            {
                "sha256": sha256,
                "variant": variant,
                "path": str(path),
                "uploaded_at": datetime.now(UTC).isoformat(),
            },
            allow_unicode=True,
            sort_keys=False,
        ),
        encoding="utf-8",
    )
    return receipt


def upload_cv(page: Page, path: Path) -> None:
    """Attach the PDF on Indeed's own CV page, never on whatever tab was open."""
    page.goto(INDEED_RESUME, wait_until="domcontentloaded")
    try:
        page.wait_for_selector(FILE_INPUT, state="attached", timeout=15_000)
    except Exception as exc:  # noqa: BLE001 — a page without the control is not the CV page
        raise IndeedCvUploadError(NO_FILE_CONTROL) from exc
    page.set_input_files(FILE_INPUT, str(path))


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
