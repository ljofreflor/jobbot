"""Project local preferences onto Indeed's Preferencias tab and type them there."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from jobbot.adapters.indeed.resume_edit import (
    PREFERENCES_TAB_MISSING,
    IndeedUiChanged,
    preferences_tab_missing,
)
from jobbot.adapters.indeed.selectors import INDEED_RESUME
from jobbot.jobs.eligibility import ApplicationAnswers
from jobbot.models.candidate import Candidate

if TYPE_CHECKING:
    from playwright.sync_api import Page

TITLE_LIMIT = 10
SAVE_SELECTOR = 'button[name="save"]'
PREFERENCES_TAB = "Preferencias"
PREFERENCES_FORM_MISSING = "formulario de Preferencias no encontrado"
TITLES_LABEL = "Cargos deseados"
PAY_LABEL = "Sueldo base mínimo"
JOB_TYPES_LABEL = "Tipos de empleo"
AVAILABILITY_LABEL = "Disponibilidad"


@dataclass(frozen=True)
class PreferencePlan:
    lines: tuple[str, ...]
    trimmed: int
    titles: tuple[str, ...] = ()
    pay: str | None = None
    job_types: tuple[str, ...] = ()
    available_from: str | None = None


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
    pay: str | None = None
    if (
        salary is not None
        and salary.amount is not None
        and salary.currency
        and salary.period
        and salary.basis == "gross"
    ):
        pay = str(salary.amount)
        lines.append(f"sueldo  ADD  {salary.amount} {salary.currency}/{salary.period}")
    elif salary is not None and salary.basis == "net":
        # "Sueldo base mínimo" is a gross field: a net figure is never projected onto it.
        lines.append(f"sueldo  needs_human  (líquido; Indeed pide {PAY_LABEL.casefold()})")
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
    available_from: str | None = None
    if availability is not None and availability.from_date is not None:
        available_from = availability.from_date.isoformat()
        lines.append(f"disponibilidad  ADD  {available_from}")
    else:
        lines.append("disponibilidad  needs_human")
    return PreferencePlan(
        tuple(lines),
        len(trimmed),
        titles=tuple(kept),
        pay=pay,
        job_types=tuple(answers.job_types),
        available_from=available_from,
    )


def open_preferences(page: Page) -> None:
    """Open Indeed's Preferencias tab, so nothing is typed on whatever tab was open."""
    page.goto(INDEED_RESUME, wait_until="domcontentloaded")
    if preferences_tab_missing(str(page.url), page.content()):
        raise IndeedUiChanged(PREFERENCES_TAB_MISSING)
    tab = page.get_by_role("link", name=PREFERENCES_TAB)
    if tab.count():
        tab.first.click()
    try:
        page.wait_for_selector(SAVE_SELECTOR, timeout=15_000)
    except Exception as exc:  # noqa: BLE001 — a page with no save control is not the form
        raise IndeedUiChanged(PREFERENCES_FORM_MISSING) from exc


def fill_preferences(page: Page, plan: PreferencePlan) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Type each planned value into the control its label names.

    Returns (written, missing): a label the form does not offer is left to the human
    instead of guessing which control it became.
    """
    written: list[str] = []
    missing: list[str] = []
    for label, values, multi in _planned_fields(plan):
        if not values:
            continue
        control = page.get_by_label(label)
        if not control.count():
            missing.append(label)
            continue
        target = control.first
        for value in values:
            target.fill(value)
            if multi:
                page.keyboard.press("Enter")
        written.append(label)
    return tuple(written), tuple(missing)


def save_preferences(page: Page, plan: PreferencePlan, *, confirmed: bool) -> tuple[str, ...]:
    """Type the plan on the Preferencias tab and save. A refusal leaves the page untouched.

    Returns the labels the form did not offer. Nothing typed means nothing to save.
    """
    if not confirmed:
        return ()
    open_preferences(page)
    written, missing = fill_preferences(page, plan)
    if written:
        page.click(SAVE_SELECTOR)
    return missing


def _planned_fields(plan: PreferencePlan) -> tuple[tuple[str, tuple[str, ...], bool], ...]:
    return (
        (TITLES_LABEL, plan.titles, True),
        (PAY_LABEL, (plan.pay,) if plan.pay else (), False),
        (JOB_TYPES_LABEL, plan.job_types, True),
        (AVAILABILITY_LABEL, (plan.available_from,) if plan.available_from else (), False),
    )
