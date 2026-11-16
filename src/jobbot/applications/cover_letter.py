"""A short cover letter that only restates profile facts and names the role.

A proposed paragraph (for example from a model) is kept only when every proper
name and every number in it already appears in the profile or in the role
being applied to. Otherwise the deterministic draft stays.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from jobbot.models.candidate import Candidate
from jobbot.models.job import JobPosting
from jobbot.nlp.refine import _named_entities

_NUMBER = re.compile(r"\d+(?:[.,]\d+)?")


class CoverLetterError(ValueError):
    """The package manifest is not an object this command can update."""


def fact_blob(candidate: Candidate, job: JobPosting) -> str:
    """Profile text plus the role title and employer. Nothing from the posting body."""
    parts = [
        candidate.personal.name,
        candidate.personal.headline,
        candidate.summary or "",
        job.title,
        job.company,
    ]
    for exp in candidate.experience:
        parts.extend((exp.title, exp.company))
        parts.extend(item.text for item in exp.achievements)
    return "\n".join(parts)


def unsupported_tokens(text: str, candidate: Candidate, job: JobPosting) -> tuple[str, ...]:
    """Names and numbers in ``text`` that the profile and the role do not contain."""
    blob = fact_blob(candidate, job)
    folded = blob.casefold()
    found: list[str] = []
    for entity in _named_entities(text):
        if entity.casefold() not in folded:
            found.append(entity)
    for number in _NUMBER.findall(text):
        if number not in blob:
            found.append(number)
    return tuple(found)


def draft_cover_letter(candidate: Candidate, job: JobPosting) -> str:
    """Role, latest recorded title, and one profile sentence. No email or phone."""
    lines = [f"Postulo al cargo de {job.title} en {job.company}."]
    if candidate.experience:
        role = candidate.experience[0]
        lines.append(f"El perfil registra el cargo de {role.title} en {role.company}.")
        achievement = role.achievements[0].text if role.achievements else ""
        sentence = _profile_sentence(candidate, achievement)
        if sentence:
            lines.append(sentence if sentence.endswith(".") else f"{sentence}.")
    lines.append(candidate.personal.name)
    return "\n".join(lines) + "\n"


def choose_draft(candidate: Candidate, job: JobPosting, proposed: str | None) -> str:
    """Keep ``proposed`` only when it adds no name or number the profile lacks."""
    base = draft_cover_letter(candidate, job)
    if proposed and proposed.strip() and not unsupported_tokens(proposed, candidate, job):
        text = proposed.strip()
        return text if text.endswith("\n") else f"{text}\n"
    return base


def record_manifest(manifest: Path, letter: Path) -> None:
    """Store the letter path on an existing package manifest."""
    data = json.loads(manifest.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        msg = f"{manifest} is not a manifest object"
        raise CoverLetterError(msg)
    data["cover_letter"] = str(letter)
    manifest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")


def _profile_sentence(candidate: Candidate, achievement: str) -> str:
    if candidate.summary and candidate.summary.strip():
        return candidate.summary.strip().splitlines()[0].strip()
    return achievement.strip()
