"""Project local preferences onto Indeed's Preferencias tab. Sends nothing."""

from __future__ import annotations

from dataclasses import dataclass

from jobbot.jobs.eligibility import ApplicationAnswers
from jobbot.models.candidate import Candidate

TITLE_LIMIT = 10
SAVE_SELECTOR = 'button[name="save"]'


@dataclass(frozen=True)
class PreferencePlan:
    lines: tuple[str, ...]
    trimmed: int


def desired_titles(candidate: Candidate, answers: ApplicationAnswers) -> list[str]:
    """Explicit titles win; otherwise the approved search queries, in order."""
    if answers.desired_titles:
        return list(answers.desired_titles)
    return [query.strip() for query in candidate.search_queries if query.strip()]


def plan_preferences(candidate: Candidate, answers: ApplicationAnswers) -> PreferencePlan:
    """One line per field. A missing fact is needs_human and does not drop the rest."""
    titles = desired_titles(candidate, answers)
    kept = titles[:TITLE_LIMIT]
    trimmed = titles[TITLE_LIMIT:]
    lines = [f"cargos  ADD  {title}" for title in kept]
    if trimmed:
        lines.append(
            f"recorte: {len(trimmed)} cargos quedan fuera del máximo de {TITLE_LIMIT}"
        )
    salary = answers.salary
    if (
        salary is not None
        and salary.amount is not None
        and salary.currency
        and salary.period
    ):
        lines.append(f"sueldo  ADD  {salary.amount} {salary.currency}/{salary.period}")
    else:
        lines.append("sueldo  needs_human")
    if answers.job_types:
        lines.append("tipos  ADD  " + ", ".join(answers.job_types))
    else:
        lines.append("tipos  needs_human")
    if answers.relocation is not None:
        lines.append(f"reubicacion  ADD  {answers.relocation}")
    else:
        lines.append("reubicacion  needs_human")
    availability = answers.availability
    if availability is not None and availability.from_date is not None:
        lines.append(f"disponibilidad  ADD  {availability.from_date.isoformat()}")
    else:
        lines.append("disponibilidad  needs_human")
    return PreferencePlan(tuple(lines), len(trimmed))


def save_preferences(page: object, *, confirmed: bool) -> None:
    """Click save only after a yes. A refused confirmation leaves the page untouched."""
    if not confirmed:
        return
    click = getattr(page, "click", None)
    if click is None:
        msg = "la página no acepta un clic"
        raise RuntimeError(msg)
    click(SAVE_SELECTOR)
