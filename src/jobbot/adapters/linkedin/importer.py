"""Merge a stored LinkedIn snapshot into an existing profile.

The snapshot has no person name, so this cannot create ``profile.yaml``.
A role whose date is only a year is skipped: inventing the month would be a fact.
Roles the snapshot omits stay in the profile.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from jobbot.models.candidate import Candidate
from jobbot.models.external_profile import ExternalProfile

_MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_SECTIONS = frozenset({"headline", "experience", "education", "skills"})


class LinkedInImportError(ValueError):
    """The section name is not one this import knows."""


@dataclass(frozen=True)
class ImportChange:
    """One confirmed edit. ``text`` is the snapshot fact, not a rewrite."""

    section: str
    text: str


@dataclass(frozen=True)
class ImportPlan:
    changes: tuple[ImportChange, ...]
    warnings: tuple[str, ...]


def import_plan(
    candidate: Candidate,
    external: ExternalProfile,
    *,
    section: str | None = None,
) -> ImportPlan:
    """Facts the snapshot has and the profile does not. Nothing is removed."""
    if section is not None and section not in _SECTIONS:
        known = ", ".join(sorted(_SECTIONS))
        msg = f"unknown section {section!r}; expected one of: {known}"
        raise LinkedInImportError(msg)
    changes: list[ImportChange] = []
    warnings: list[str] = []
    headline = (external.headline or "").strip()
    if section in {None, "headline"} and headline and headline != candidate.personal.headline:
        changes.append(ImportChange("headline", headline))
    if section in {None, "experience"}:
        changes.extend(_experience(candidate, external, warnings))
    if section in {None, "education"}:
        changes.extend(_education(candidate, external, warnings))
    if section in {None, "skills"}:
        changes.extend(_skills(candidate, external))
    if not changes and not warnings and _sparse(external):
        warnings.append("sparse snapshot; nothing to import")
    return ImportPlan(tuple(changes), tuple(warnings))


def render_change(change: ImportChange) -> str:
    """One review line. Experience and education show the snapshot's own fields."""
    if change.section == "experience":
        company, title, start, end = change.text.split("\t")
        when = f"{start}–{end}" if end else start
        return f"experience  {company} / {title}  {when}"
    if change.section == "education":
        institution, degree, start = change.text.split("\t")
        suffix = f"  {start}" if start else ""
        return f"education  {institution} / {degree}{suffix}"
    if change.section == "skills":
        return f"skills  {change.text}"
    return f"headline  {change.text}"


def apply_import(
    raw: dict[str, object],
    plan: ImportPlan,
    *,
    sections: set[str],
) -> dict[str, object]:
    """Copy ``raw`` and apply the changes whose section was confirmed."""
    data = dict(raw)
    personal = _mapping(data.get("personal"))
    experience = _items(data.get("experience"))
    education = _items(data.get("education"))
    skills = _mapping(data.get("skills"))
    for change in plan.changes:
        if change.section not in sections:
            continue
        if change.section == "headline":
            personal["headline"] = change.text
        elif change.section == "experience":
            experience.append(_experience_row(change.text, len(experience)))
        elif change.section == "education":
            education.append(_education_row(change.text, len(education)))
        elif change.section == "skills":
            bucket = [item for item in _items(skills.get("other")) if isinstance(item, str)]
            if change.text not in bucket:
                bucket.append(change.text)
            skills["other"] = bucket
    data["personal"] = personal
    data["experience"] = experience
    data["education"] = education
    data["skills"] = skills
    return data


def _mapping(value: object) -> dict[str, object]:
    if isinstance(value, dict):
        return dict(value)
    return {}


def _items(value: object) -> list[object]:
    if isinstance(value, list):
        return list(value)
    return []


def _sparse(external: ExternalProfile) -> bool:
    return not any(
        (
            (external.headline or "").strip(),
            external.experience,
            external.education,
            external.skills,
        )
    )


def _experience(
    candidate: Candidate,
    external: ExternalProfile,
    warnings: list[str],
) -> list[ImportChange]:
    owned = {(exp.company.casefold(), exp.title.casefold()) for exp in candidate.experience}
    changes: list[ImportChange] = []
    for item in external.experience:
        company = (item.company or "").strip()
        title = (item.title or "").strip()
        if not company or not title:
            continue
        if (company.casefold(), title.casefold()) in owned:
            continue
        start = (item.start_date or "").strip()
        if not _MONTH.fullmatch(start):
            warnings.append(f"experience skipped, date is not YYYY-MM: {company} / {title}")
            continue
        end = (item.end_date or "").strip()
        end_part = end if _MONTH.fullmatch(end) else ""
        changes.append(ImportChange("experience", f"{company}\t{title}\t{start}\t{end_part}"))
    return changes


def _education(
    candidate: Candidate,
    external: ExternalProfile,
    warnings: list[str],
) -> list[ImportChange]:
    owned = {(edu.institution.casefold(), edu.degree.casefold()) for edu in candidate.education}
    changes: list[ImportChange] = []
    for item in external.education:
        institution = (item.institution or "").strip()
        degree = (item.degree or "").strip()
        if not institution or not degree:
            warnings.append("education skipped, institution or degree is missing")
            continue
        if (institution.casefold(), degree.casefold()) in owned:
            continue
        start = (item.start_date or "").strip()
        start_part = start if _MONTH.fullmatch(start) else ""
        if start and not start_part:
            warnings.append(f"education date ignored, not YYYY-MM: {institution}")
        changes.append(ImportChange("education", f"{institution}\t{degree}\t{start_part}"))
    return changes


def _skills(candidate: Candidate, external: ExternalProfile) -> list[ImportChange]:
    owned = {name.casefold() for name in candidate.skills.all_skills()}
    changes: list[ImportChange] = []
    for name in external.skills:
        label = name.strip()
        if label and label.casefold() not in owned:
            changes.append(ImportChange("skills", label))
            owned.add(label.casefold())
    return changes


def _experience_row(text: str, index: int) -> dict[str, object]:
    company, title, start, end = text.split("\t")
    row: dict[str, object] = {
        "id": f"linkedin-{index + 1}",
        "company": company,
        "title": title,
        "start_date": start,
        "current": not end,
        "achievements": [],
    }
    if end:
        row["end_date"] = end
    return row


def _education_row(text: str, index: int) -> dict[str, object]:
    institution, degree, start = text.split("\t")
    row: dict[str, object] = {
        "id": f"linkedin-edu-{index + 1}",
        "institution": institution,
        "degree": degree,
    }
    if start:
        row["start_date"] = start
    return row
