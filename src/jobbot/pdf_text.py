"""Text layer of a PDF, shared by postings. The CV importer keeps its own path reader."""

from __future__ import annotations

from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from jobbot.profile.pdf_glyphs import repair_missing_ligatures


class PdfTextError(Exception):
    """The bytes are not a PDF pypdf can read."""


def text_from_pdf_bytes(data: bytes) -> str:
    """Every page's text layer. Empty when the file is only an image."""
    try:
        reader = PdfReader(BytesIO(data))
        repair_missing_ligatures(reader)
        pages = [page.extract_text() or "" for page in reader.pages]
    except (PdfReadError, OSError, ValueError) as exc:
        msg = f"no se pudo leer el PDF: {exc}"
        raise PdfTextError(msg) from exc
    return "\n".join(pages)
