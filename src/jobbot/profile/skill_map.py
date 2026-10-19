"""Which declared skills a role or a degree already shows. Never invents a skill."""

from __future__ import annotations

from dataclasses import dataclass

from jobbot.jobs.normalization import cognate_key, concept_of, fold_text
from jobbot.models.candidate import Candidate
from jobbot.models.skill import SkillEvidence


@dataclass(frozen=True)
class SkillUse:
    """One place the profile already shows a declared skill."""

    skill: str
    experience_id: str | None
    achievement_id: str | None
    education_id: str | None


def map_skills(candidate: Candidate) -> list[SkillUse]:
    """Skills the profile already names, tied to the role or degree that shows them."""
    uses: list[SkillUse] = []
    for skill in candidate.skills.all_skills():
        for exp in candidate.experience:
            if exp.description and _backs(skill, exp.description):
                uses.append(SkillUse(skill, exp.id, None, None))
            for ach in exp.achievements:
                blob = " ".join([*ach.tags, ach.text, *ach.metrics.keys()])
                if _backs(skill, blob):
                    uses.append(SkillUse(skill, exp.id, ach.id, None))
        for edu in candidate.education:
            blob = " ".join(part for part in (edu.degree, edu.details, edu.institution) if part)
            if _backs(skill, blob):
                uses.append(SkillUse(skill, None, None, edu.id))
    return uses


def unbacked_skills(candidate: Candidate, uses: list[SkillUse] | None = None) -> list[str]:
    """Declared skills no role, achievement or degree shows."""
    found = {use.skill for use in (uses if uses is not None else map_skills(candidate))}
    return [skill for skill in candidate.skills.all_skills() if skill not in found]


def unbacked_achievements(candidate: Candidate, uses: list[SkillUse] | None = None) -> list[str]:
    """Achievements that show no declared skill."""
    found = {
        use.achievement_id
        for use in (uses if uses is not None else map_skills(candidate))
        if use.achievement_id
    }
    return [
        ach.id
        for exp in candidate.experience
        for ach in exp.achievements
        if ach.id not in found
    ]


def evidence_records(uses: list[SkillUse]) -> list[SkillEvidence]:
    """Group uses by the skill string already stored. Adds no skill."""
    grouped: dict[str, SkillEvidence] = {}
    for use in uses:
        row = grouped.get(use.skill)
        if row is None:
            row = SkillEvidence(skill=use.skill)
            grouped[use.skill] = row
        if use.experience_id and use.experience_id not in row.experience_ids:
            row.experience_ids.append(use.experience_id)
        if use.achievement_id and use.achievement_id not in row.achievement_ids:
            row.achievement_ids.append(use.achievement_id)
        if use.education_id and use.education_id not in row.education_ids:
            row.education_ids.append(use.education_id)
    return list(grouped.values())


def format_map(uses: list[SkillUse]) -> list[str]:
    lines: list[str] = []
    for use in uses:
        where = use.experience_id or use.education_id or ""
        evidence = use.achievement_id or use.education_id or where
        lines.append(f"{use.skill} -> {where} ({evidence})")
    return lines


def format_unbacked(candidate: Candidate) -> list[str]:
    uses = map_skills(candidate)
    lines = [f"unbacked skill: {skill}" for skill in unbacked_skills(candidate, uses)]
    lines.extend(
        f"unbacked achievement: {ach_id}" for ach_id in unbacked_achievements(candidate, uses)
    )
    return lines


# Glue inside a skill name ('gestión de redes'): no role shows a skill by saying 'de'.
_CONNECTORS = frozenset(
    {"de", "del", "la", "las", "los", "el", "y", "e", "en", "of", "the", "and", "in", "for"}
)


def _words(text: str) -> set[str]:
    """The words that carry the claim. A short name ('SQL', 'BI', 'R') is one of them."""
    return {word for word in fold_text(text.replace("_", " ")).split() if word not in _CONNECTORS}


def _same(left: str, right: str) -> bool:
    if left == right or cognate_key(left) == cognate_key(right):
        return True
    left_concept = concept_of(left)
    return left_concept is not None and left_concept == concept_of(right)


def _backs(skill: str, blob: str) -> bool:
    needles = _words(skill)
    if not needles:
        return False
    haystack = _words(blob)
    return all(any(_same(needle, word) for word in haystack) for needle in needles)
