"""A derived translation may rephrase. It may not change a figure, a name, or add a skill."""

from __future__ import annotations

from jobbot.models.candidate import Candidate
from jobbot.profile.overlay import base_texts, overlay_problems


def translation_problems(candidate: Candidate, texts: dict[str, str]) -> list[str]:
    """Unknown ids, changed numbers, a dropped company name, or a skill the source lacks."""
    problems = list(overlay_problems(candidate, texts))
    base = base_texts(candidate)
    companies = [exp.company for exp in candidate.experience if exp.company.strip()]
    skills = [skill for skill in candidate.skills.all_skills() if len(skill.casefold()) >= 4]
    for key, phrase in texts.items():
        original = base.get(key)
        if original is None:
            continue
        problems.extend(_name_problems(key, original, phrase, companies))
        problems.extend(_skill_problems(key, original, phrase, skills))
    return problems


def _name_problems(key: str, original: str, phrase: str, companies: list[str]) -> list[str]:
    source = original.casefold()
    translated = phrase.casefold()
    missing = [
        company
        for company in companies
        if company.casefold() in source and company.casefold() not in translated
    ]
    if not missing:
        return []
    return [f"{key}: missing name"]


def _skill_problems(key: str, original: str, phrase: str, skills: list[str]) -> list[str]:
    source = original.casefold()
    translated = phrase.casefold()
    extra = [
        skill
        for skill in skills
        if skill.casefold() in translated and skill.casefold() not in source
    ]
    if not extra:
        return []
    return [f"{key}: extra skill"]
