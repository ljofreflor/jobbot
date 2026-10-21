"""Pasted employer messages become application events. No inbox, no invented motive.

The human pastes the text. Rules classify it. A stored posting is linked when its
title and employer both appear. Otherwise the message can register a minimal
external posting. ``offer`` is not overwritten by a rejection unless the human
confirms. The original text is stored only under ``.local/``, with contact redacted.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

import yaml
from sqlalchemy.orm import Session

from jobbot.applications.manager import ApplicationRepository
from jobbot.jobs.repository import JobRepository
from jobbot.models.application import Application, ApplicationStatus
from jobbot.models.job import JobPosting
from jobbot.ops.pii_guard import redact

_ACTION = "actualizar preferencias del perfil en el portal"

_ACTION_PHRASES: tuple[str, ...] = (
    "preference section",
    "job posting notifications",
    "preferencias del perfil",
    "alertas de empleo",
)

_ROLE_PATTERNS: tuple[str, ...] = (
    r"the (.+?) position at ([^.\n]+)",
    r"cargo\s+(.+?)\s+en\s+([^.\n]+)",
)


class FeedbackKind(StrEnum):
    """What the pasted message says happened. Not a guess about why."""

    ACKNOWLEDGED = "acknowledged"
    REJECTED_NO_INTERVIEW = "rejected_no_interview"
    REJECTED_AFTER_INTERVIEW = "rejected_after_interview"
    SCREENING_OR_TEST = "screening_or_test"
    INTERVIEW = "interview"
    OFFER = "offer"
    POSTING_CANCELLED = "posting_cancelled"


class FeedbackError(ValueError):
    """The paste cannot be registered. Not an ops defect."""


_RULES: tuple[tuple[FeedbackKind, tuple[str, ...]], ...] = (
    (
        FeedbackKind.REJECTED_AFTER_INTERVIEW,
        (
            "after the interview",
            "after your interview",
            "following your interview",
            "tras la entrevista",
            "despues de la entrevista",
        ),
    ),
    (
        FeedbackKind.REJECTED_NO_INTERVIEW,
        (
            "not retained",
            "not selected",
            "was unsuccessful",
            "not be moving forward",
            "not moving forward",
            "no has sido seleccionad",
            "no fue seleccionad",
            "lamentamos informar",
            "we regret to inform",
        ),
    ),
    (
        FeedbackKind.POSTING_CANCELLED,
        (
            "position has been cancelled",
            "position has been canceled",
            "proceso cancelado",
            "aviso cancelado",
        ),
    ),
    (
        FeedbackKind.OFFER,
        (
            "pleased to offer",
            "offer of employment",
            "oferta de trabajo",
            "te ofrecemos el puesto",
        ),
    ),
    (
        FeedbackKind.INTERVIEW,
        (
            "invite you to an interview",
            "invitation to interview",
            "schedule an interview",
            "te invitamos a una entrevista",
            "entrevista el",
        ),
    ),
    (
        FeedbackKind.SCREENING_OR_TEST,
        (
            "online assessment",
            "complete the assessment",
            "prueba en linea",
        ),
    ),
    (
        FeedbackKind.ACKNOWLEDGED,
        (
            "we have received your application",
            "application has been received",
            "thank you for applying",
            "hemos recibido tu postulacion",
            "hemos recibido su postulacion",
        ),
    ),
)

_STATUS_FOR: dict[FeedbackKind, ApplicationStatus | None] = {
    FeedbackKind.ACKNOWLEDGED: None,
    FeedbackKind.REJECTED_NO_INTERVIEW: ApplicationStatus.REJECTED,
    FeedbackKind.REJECTED_AFTER_INTERVIEW: ApplicationStatus.REJECTED,
    FeedbackKind.POSTING_CANCELLED: ApplicationStatus.REJECTED,
    FeedbackKind.SCREENING_OR_TEST: ApplicationStatus.SCREENING,
    FeedbackKind.INTERVIEW: ApplicationStatus.INTERVIEW,
    FeedbackKind.OFFER: ApplicationStatus.OFFER,
}


@dataclass(frozen=True)
class FeedbackReading:
    """What a dry-run shows. ``job_id`` empty means a new external posting."""

    kind: FeedbackKind
    evidence: str
    title: str
    employer: str
    when: str
    actions: tuple[str, ...]
    job_id: str
    current_status: str
    next_status: str
    needs_confirm: bool

    def lines(self) -> tuple[str, ...]:
        aviso = self.job_id or "(nuevo)"
        estado = self.next_status or f"sin cambio ({self.current_status or '—'})"
        rows = [
            f"clase: {self.kind.value}",
            f"evidencia: {self.evidence}",
            f"aviso: {aviso}  {self.title} — {self.employer}",
            f"estado: {estado}",
            "motivo: el mensaje no lo trae",
        ]
        if self.when:
            rows.append(f"cuando: {self.when}")
        if self.actions:
            rows.append("accion: " + "; ".join(self.actions))
        if self.needs_confirm:
            rows.append(
                "confirmacion: la postulacion esta en offer; un rechazo no la pisa sin --yes"
            )
        return tuple(rows)


@dataclass(frozen=True)
class FunnelRow:
    """One stored posting in the funnel. The group is the title, not a profession."""

    title: str
    employer: str
    portal: str
    applications: int
    responses: int
    interviews: int
    rejections: int

    def line(self) -> str:
        return (
            f"{self.title} | {self.employer} | {self.portal} | "
            f"{self.applications} | {self.responses} | {self.interviews} | {self.rejections}"
        )


def classify(text: str) -> tuple[FeedbackKind, str]:
    """The first structural phrase that matches, with the phrase as evidence."""
    folded = _fold(text)
    for kind, phrases in _RULES:
        for phrase in phrases:
            if _fold(phrase) in folded:
                return kind, phrase
    msg = "no structural phrase in the message; nothing was classified"
    raise FeedbackError(msg)


def read_feedback(
    text: str,
    jobs: list[JobPosting],
    applications: list[Application],
    *,
    job_id: str | None = None,
) -> FeedbackReading:
    """Pure reading. Does not write."""
    kind, evidence = classify(text)
    title, employer = _role_from(text)
    matched = _match_job(text, jobs, job_id)
    if matched is not None:
        title = matched.title
        employer = matched.company
    elif not title or not employer:
        msg = "the message names no stored posting and no role to register"
        raise FeedbackError(msg)
    current = _application_for(applications, matched.id if matched else "")
    current_status = current.status.value if current else ""
    nxt = _STATUS_FOR[kind]
    needs_confirm = (
        current is not None
        and current.status is ApplicationStatus.OFFER
        and nxt is not None
        and nxt is not ApplicationStatus.OFFER
    )
    return FeedbackReading(
        kind=kind,
        evidence=evidence,
        title=title.strip(),
        employer=employer.strip(),
        when=_when(text) if kind is FeedbackKind.INTERVIEW else "",
        actions=_actions(text),
        job_id=matched.id if matched else "",
        current_status=current_status,
        next_status="" if nxt is None else nxt.value,
        needs_confirm=needs_confirm,
    )


def store_feedback(
    session: Session,
    root: Path,
    reading: FeedbackReading,
    body: str,
) -> str:
    """Write the redacted paste, the event, and the status. Returns the job id."""
    redacted = redact(body)
    _write_paste(root, redacted)
    jobs = JobRepository(session)
    if reading.job_id:
        job = jobs.get(reading.job_id)
        if job is None:
            msg = f"job not found: {reading.job_id}"
            raise FeedbackError(msg)
    else:
        job = jobs.upsert_external(
            JobPosting(
                id="PENDING",
                source="external",
                title=reading.title,
                company=reading.employer,
                description="Registered from a pasted employer message.",
            )
        )
    apps = ApplicationRepository(session)
    existing = apps.get_for_job(job.id)
    status = _STATUS_FOR[reading.kind]
    if status is None:
        if existing is None:
            existing = apps.upsert_for_job(job.id, status=ApplicationStatus.APPLIED)
        apps.add_event(existing.id, "feedback", _detail(reading))
    else:
        saved = apps.upsert_for_job(job.id, status=status)
        apps.add_event(saved.id, "feedback", _detail(reading))
    if reading.kind is FeedbackKind.INTERVIEW and reading.when:
        _remember_interview(root, job_id=job.id, title=job.title, when=reading.when)
    return job.id


def funnel(session: Session) -> tuple[FunnelRow, ...]:
    """Counts per stored posting. A title is not a profession family."""
    jobs = JobRepository(session).list_all()
    apps = ApplicationRepository(session)
    by_job = {app.job_id: app for app in apps.list_all()}
    rows: list[FunnelRow] = []
    for job in jobs:
        app = by_job.get(job.id)
        if app is None:
            continue
        events = apps.events_for(app.id)
        responses = sum(1 for event in events if event.event_type == "feedback")
        interviews = int(
            app.status is ApplicationStatus.INTERVIEW
            or any((event.detail or "").startswith("interview|") for event in events)
        )
        rejections = int(app.status is ApplicationStatus.REJECTED)
        portal = job.ats_kind or job.source
        rows.append(
            FunnelRow(
                title=job.title,
                employer=job.company,
                portal=portal,
                applications=1,
                responses=responses,
                interviews=interviews,
                rejections=rejections,
            )
        )
    return tuple(rows)


def report_lines(rows: tuple[FunnelRow, ...]) -> tuple[str, ...]:
    header = "cargo | empleador | portal | postulaciones | respuestas | entrevistas | rechazos"
    return (header, *(row.line() for row in rows))


def interview_reminders(root: Path) -> tuple[str, ...]:
    """Lines for ``jobbot status``. Empty when nobody stored an interview date."""
    path = _reminders_path(root)
    if not path.is_file():
        return ()
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    if not isinstance(loaded, list):
        return ()
    lines: list[str] = []
    for item in loaded:
        if not isinstance(item, dict):
            continue
        when = str(item.get("date") or "")
        job_id = str(item.get("job_id") or "")
        title = str(item.get("title") or "")
        if when and job_id:
            lines.append(f"entrevista {when}  {job_id}  {title}")
    return tuple(lines)


def _detail(reading: FeedbackReading) -> str:
    when = reading.when or "-"
    return redact(f"{reading.kind.value}|{when}|{reading.evidence}")


def _application_for(applications: list[Application], job_id: str) -> Application | None:
    if not job_id:
        return None
    for app in applications:
        if app.job_id == job_id:
            return app
    return None


def _match_job(text: str, jobs: list[JobPosting], job_id: str | None) -> JobPosting | None:
    if job_id:
        for job in jobs:
            if job.id == job_id:
                return job
        msg = f"job not found: {job_id}"
        raise FeedbackError(msg)
    folded = _fold(text)
    hits = [
        job
        for job in jobs
        if len(job.title) >= 4
        and _fold(job.title) in folded
        and _fold(job.company) in folded
    ]
    if not hits:
        return None
    return max(hits, key=lambda job: len(job.title))


def _role_from(text: str) -> tuple[str, str]:
    for pattern in _ROLE_PATTERNS:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip(), match.group(2).strip()
    return "", ""


def _when(text: str) -> str:
    match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", text)
    return match.group(1) if match else ""


def _actions(text: str) -> tuple[str, ...]:
    folded = _fold(text)
    if any(_fold(phrase) in folded for phrase in _ACTION_PHRASES):
        return (_ACTION,)
    return ()


def _fold(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in nfkd if not unicodedata.combining(char))


def _write_paste(root: Path, redacted: str) -> None:
    folder = root / ".local" / "application-feedback"
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    (folder / f"{stamp}.txt").write_text(redacted, encoding="utf-8")


def _reminders_path(root: Path) -> Path:
    return root / ".local" / "interview-reminders.yaml"


def _remember_interview(root: Path, *, job_id: str, title: str, when: str) -> None:
    path = _reminders_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else []
    rows = list(loaded) if isinstance(loaded, list) else []
    if not any(isinstance(item, dict) and item.get("job_id") == job_id for item in rows):
        rows.append({"date": when, "job_id": job_id, "title": title})
    path.write_text(yaml.safe_dump(rows, sort_keys=False, allow_unicode=True), encoding="utf-8")
