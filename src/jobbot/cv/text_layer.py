"""The text an ATS reads from a CV. Icons and stuffed terms are findings, not facts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from jobbot.cv.selection import profile_facts_text
from jobbot.jobs.normalization import fold_text
from jobbot.models.candidate import Candidate
from jobbot.models.job import JobPosting
from jobbot.pdf_text import text_from_pdf_bytes

_PUA = re.compile(r"[\uE000-\uF8FF]")
_ALLOWED_BULLETS = frozenset({"•", "-", "–"})
# Font-awesome bullets often survive as one of these letters, glued to the line.
_ICON_LETTERS = frozenset({"f", "a", "Ȳ"})
_SEPARATORS = frozenset(" \t\r\n\f\v|•-–—:·/( ")
# A contact only counts where it stands on its own: the handle "ana" inside
# "ana@example.com" or "ana-ejemplo" is not the LinkedIn contact.
_JOINERS = frozenset("@._-+")
_BULLET_LINE = re.compile(r"^(\S)\s+\S")


@dataclass(frozen=True)
class TextLayerIssue:
    """One problem in the text layer. The detail names the kind, not a secret."""

    kind: str
    detail: str


def check_text_layer(
    pdf_path: Path,
    candidate: Candidate,
    *,
    job: JobPosting | None = None,
) -> list[TextLayerIssue]:
    """Read a PDF's text layer and report icons, missing contact, and stuffed terms."""
    text = text_from_pdf_bytes(Path(pdf_path).read_bytes())
    return issues_in_text(text, candidate, job=job)


def issues_in_text(
    text: str,
    candidate: Candidate,
    *,
    job: JobPosting | None = None,
) -> list[TextLayerIssue]:
    """The same checks on text that is already extracted."""
    issues: list[TextLayerIssue] = []
    if _PUA.search(text) or _glued_icon(text, candidate):
        issues.append(TextLayerIssue("icon_glyph", "icon glyph before contact"))
    if _bad_bullet(text):
        issues.append(TextLayerIssue("bullet_glyph", "bullet is not a plain mark"))
    issues.extend(_missing_contact(text, candidate))
    if job is not None:
        issues.extend(_stuffed(text, candidate, job))
    return issues


def issues_for_outputs(
    paths: list[Path],
    candidate: Candidate,
    job: JobPosting | None = None,
) -> list[TextLayerIssue]:
    """Check a built PDF and, when there is no PDF, the ATS text."""
    found: list[TextLayerIssue] = []
    seen: set[tuple[str, str]] = set()
    pdfs = [path for path in paths if path.suffix == ".pdf"]
    texts = pdfs or [path for path in paths if path.name == "cv_ats.txt"]
    for path in texts:
        if not path.is_file():
            continue
        if path.suffix == ".pdf":
            batch = check_text_layer(path, candidate, job=job)
        else:
            batch = issues_in_text(path.read_text(encoding="utf-8"), candidate, job=job)
        for issue in batch:
            key = (issue.kind, issue.detail)
            if key not in seen:
                seen.add(key)
                found.append(issue)
    return found


def _glued_icon(text: str, candidate: Candidate) -> bool:
    for _label, value in _contacts(candidate):
        spots = _occurrences(text, value)
        if spots and all(at > 0 and text[at - 1] not in _SEPARATORS for at in spots):
            return True
    return False


def _occurrences(text: str, value: str) -> list[int]:
    """Offsets where the value is a whole token, not a piece of a longer one."""
    spots: list[int] = []
    at = text.find(value)
    while at != -1:
        before = text[at - 1 : at]
        after = text[at + len(value) : at + len(value) + 1]
        if before not in _JOINERS and after not in _JOINERS:
            spots.append(at)
        at = text.find(value, at + 1)
    return spots


def _bad_bullet(text: str) -> bool:
    for line in text.splitlines():
        found = _BULLET_LINE.match(line.strip())
        if found is None:
            continue
        marker = found.group(1)
        if marker in _ALLOWED_BULLETS:
            continue
        if marker in _ICON_LETTERS or _PUA.match(marker) or not marker.isalnum():
            return True
    return False


def _missing_contact(text: str, candidate: Candidate) -> list[TextLayerIssue]:
    missing: list[TextLayerIssue] = []
    for label, value in _contacts(candidate):
        if value and not _occurrences(text, value):
            missing.append(
                TextLayerIssue("contact_missing", f"{label} missing from the text layer")
            )
    return missing


def _stuffed(text: str, candidate: Candidate, job: JobPosting) -> list[TextLayerIssue]:
    haystack = fold_text(profile_facts_text(candidate))
    page = fold_text(text)
    issues: list[TextLayerIssue] = []
    for skill in job.skills:
        needle = fold_text(skill)
        if len(needle) < 3 or _present(needle, haystack):
            continue
        if _present(needle, page):
            issues.append(TextLayerIssue("unsupported_term", skill))
    return issues


def _present(needle: str, haystack: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", haystack) is not None


def _contacts(candidate: Candidate) -> list[tuple[str, str]]:
    personal = candidate.personal
    found: list[tuple[str, str]] = []
    if personal.email:
        found.append(("email", str(personal.email)))
    if personal.phone:
        found.append(("phone", personal.phone))
    if personal.linkedin:
        handle = personal.linkedin.rstrip("/").rsplit("/", 1)[-1]
        found.append(("linkedin", handle))
    return found
