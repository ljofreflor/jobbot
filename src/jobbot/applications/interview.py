"""Interview questions from the package that was sent (#203).

The questions come from the archived posting. The only evidence is an achievement
or a role that ``selection.json`` already kept for that application. A requirement
with no overlap is an honest bridge to a role that was sent — never a new achievement.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from jobbot.cv.selection import SelectedAchievement, SelectionResult
from jobbot.jobs.language import detect_language
from jobbot.jobs.normalization import fold_text
from jobbot.matching.analyzer import _STOPWORDS
from jobbot.models.candidate import Candidate
from jobbot.models.experience import Achievement, Experience
from jobbot.models.job import JobPosting

_MIN_WORD = 4


@dataclass(frozen=True)
class InterviewCard:
    """One posting requirement, plus evidence that was already sent or a bridge."""

    requirement: str
    question: str
    evidence_id: str | None = None
    evidence_text: str | None = None
    bridge: str | None = None


def sent_selection_path(output_dir: Path, job_id: str) -> Path | None:
    """The selection copied into the application package, else the job CV's own."""
    base = output_dir / "jobs" / job_id
    for path in (base / "application" / "selection.json", base / "selection.json"):
        if path.is_file():
            return path
    return None


def load_sent_selection(path: Path) -> SelectionResult:
    """Read the ids that were sent. Unknown keys are ignored."""
    data = json.loads(path.read_text(encoding="utf-8"))
    achievements = [
        SelectedAchievement(id=str(item["id"]), reason=[str(r) for r in item.get("reason") or []])
        for item in data.get("selected_achievements") or []
        if isinstance(item, dict) and item.get("id")
    ]
    return SelectionResult(
        experience_ids=[str(item) for item in data.get("experience_ids") or []],
        selected_achievements=achievements,
        skill_names=[str(item) for item in data.get("skill_names") or []],
        job_id=str(data["job_id"]) if data.get("job_id") else None,
    )


def cards_for(
    job: JobPosting,
    candidate: Candidate,
    selection: SelectionResult,
) -> list[InterviewCard]:
    """One card per archived requirement. Evidence is limited to the sent selection."""
    requirements = [item.strip() for item in job.requirements if item.strip()]
    if not requirements:
        requirements = [item.strip() for item in job.skills if item.strip()]
    sent_achievements = _sent_achievements(candidate, selection)
    sent_roles = _sent_roles(candidate, selection)
    return [
        _card(requirement, sent_achievements, sent_roles)
        for requirement in requirements
    ]


def format_cards(cards: list[InterviewCard]) -> str:
    """Plain text for the terminal. No story is written."""
    if not cards:
        return "sin requisitos en el aviso archivado"
    lines: list[str] = []
    for index, card in enumerate(cards, start=1):
        lines.append(f"{index}. {card.requirement}")
        lines.append(f"   pregunta: {card.question}")
        if card.evidence_id and card.evidence_text:
            lines.append(f"   evidencia: {card.evidence_id}: {card.evidence_text}")
        else:
            lines.append(f"   puente: {card.bridge}")
    return "\n".join(lines)


def _card(
    requirement: str,
    achievements: list[Achievement],
    roles: list[Experience],
) -> InterviewCard:
    question = _question(requirement)
    best_achievement = _best(requirement, [(ach.id, ach.text) for ach in achievements])
    if best_achievement is not None:
        evidence_id, evidence_text = best_achievement
        return InterviewCard(
            requirement=requirement,
            question=question,
            evidence_id=evidence_id,
            evidence_text=evidence_text,
        )
    best_role = _best(
        requirement,
        [(role.id, _role_blob(role)) for role in roles],
    )
    if best_role is not None:
        role = next(item for item in roles if item.id == best_role[0])
        return InterviewCard(
            requirement=requirement,
            question=question,
            evidence_id=role.id,
            evidence_text=f"{role.title} — {role.company}",
        )
    return InterviewCard(
        requirement=requirement,
        question=question,
        bridge=_bridge(requirement, roles[0] if roles else None),
    )


def _question(requirement: str) -> str:
    if detect_language(requirement) == "en":
        return f"How did you do this: {requirement}?"
    return f"¿Cómo lo ejerciste: {requirement}?"


def _bridge(requirement: str, role: Experience | None) -> str:
    english = detect_language(requirement) == "en"
    if role is None:
        return "I have not done this" if english else "no lo ejercí"
    if english:
        return f"I have not done this; nearby: {role.title} at {role.company}"
    return f"no lo ejercí; sí {role.title} en {role.company}"


def _best(requirement: str, options: list[tuple[str, str]]) -> tuple[str, str] | None:
    wanted = _words(requirement)
    if not wanted:
        return None
    ranked = [
        (len(wanted & _words(text)), index, item_id, text)
        for index, (item_id, text) in enumerate(options)
    ]
    ranked = [item for item in ranked if item[0] > 0]
    if not ranked:
        return None
    ranked.sort(key=lambda item: (-item[0], item[1]))
    _score, _index, item_id, text = ranked[0]
    return item_id, text


def _words(text: str) -> set[str]:
    """Content words only: sharing 'experiencia' is not having exercised the requirement."""
    return {
        word
        for word in fold_text(text).split()
        if len(word) >= _MIN_WORD and word not in _STOPWORDS
    }


def _role_blob(role: Experience) -> str:
    return " ".join(part for part in (role.title, role.company, role.description) if part)


def _sent_achievements(candidate: Candidate, selection: SelectionResult) -> list[Achievement]:
    allowed = {item.id for item in selection.selected_achievements}
    return [
        ach
        for exp in candidate.experience
        for ach in exp.achievements
        if ach.id in allowed
    ]


def _sent_roles(candidate: Candidate, selection: SelectionResult) -> list[Experience]:
    allowed = set(selection.experience_ids)
    return [exp for exp in candidate.experience if exp.id in allowed]
