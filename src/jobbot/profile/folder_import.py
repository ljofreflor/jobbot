"""A folder of CVs proposes role ids. It does not write the profile."""

from __future__ import annotations

from pathlib import Path

from jobbot.profile.importer_pdf import PdfImportError, import_pdf_cv


def classify_role_ids(stored: set[str], incoming: list[str]) -> tuple[list[str], list[str]]:
    """New ids, then ids that would replace a stored role. A repeated id counts once."""
    seen: set[str] = set()
    new: list[str] = []
    conflict: list[str] = []
    for role_id in incoming:
        if role_id in seen:
            continue
        seen.add(role_id)
        if role_id in stored:
            conflict.append(role_id)
        else:
            new.append(role_id)
    return new, conflict


def role_ids_in_pdf(path: Path) -> list[str]:
    """Experience ids from one PDF. Raises PdfImportError when the file cannot be read."""
    result = import_pdf_cv(path)
    experience = result.data.get("experience")
    if not isinstance(experience, list):
        return []
    ids: list[str] = []
    for item in experience:
        if isinstance(item, dict) and isinstance(item.get("id"), str):
            ids.append(item["id"])
    return ids


def pdfs_in(folder: Path) -> list[Path]:
    found = [path for path in folder.iterdir() if path.is_file() and path.suffix.lower() == ".pdf"]
    return sorted(found)


def folder_report(folder: Path, stored: set[str]) -> tuple[list[str], list[str], list[str]]:
    """New ids, conflicts, and PDF names that could not be read."""
    incoming: list[str] = []
    unread: list[str] = []
    for path in pdfs_in(folder):
        try:
            incoming.extend(role_ids_in_pdf(path))
        except PdfImportError:
            unread.append(path.name)
    new, conflict = classify_role_ids(stored, incoming)
    return new, conflict, unread
