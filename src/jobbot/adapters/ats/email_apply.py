"""Email apply drafts and Gmail compose HITL (user presses Send)."""

from __future__ import annotations

import webbrowser
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote

from jobbot.models.candidate import Candidate
from jobbot.models.job import JobPosting

# Gmail compose query strings blow up past ~2k; keep body usable.
_MAX_BODY_IN_URL = 1500


@dataclass(frozen=True)
class EmailApplyDraft:
    to: str
    subject: str
    body: str
    cv_path: Path | None
    job_id: str
    body_truncated_for_url: bool = False


def _recipient_from_job(job: JobPosting) -> str | None:
    raw = (job.ats_url or "").strip()
    if raw.lower().startswith("mailto:"):
        return raw.split(":", 1)[1].split("?", 1)[0].strip() or None
    if job.ats_kind == "email" and "@" in raw:
        return raw
    return None


def build_email_draft(
    candidate: Candidate,
    job: JobPosting,
    *,
    cv_path: Path | None = None,
) -> EmailApplyDraft:
    """Compose apply email from Candidate facts + job description (= post/JD text)."""
    to = _recipient_from_job(job)
    if not to:
        msg = "Job has no mailto apply address"
        raise ValueError(msg)
    name = candidate.personal.name
    subject = f"Postulación: {job.title} — {name}"
    headline = candidate.personal.headline or ""
    summary = (candidate.summary or "").strip()
    intro_parts = [
        "Hola,",
        "",
        f"Me llamo {name}. {headline}".strip(),
    ]
    if summary:
        intro_parts.extend(["", summary])
    intro_parts.extend(
        [
            "",
            "Adjunto mi CV para el cargo indicado en el anuncio.",
            "",
            "Descripción del cargo (anuncio):",
            job.description.strip() or job.raw_description.strip() or "(sin descripción)",
            "",
            "Saludos,",
            name,
        ]
    )
    if candidate.personal.email:
        intro_parts.append(str(candidate.personal.email))
    if candidate.personal.linkedin:
        intro_parts.append(candidate.personal.linkedin)
    body = "\n".join(intro_parts)
    return EmailApplyDraft(
        to=to,
        subject=subject,
        body=body,
        cv_path=cv_path,
        job_id=job.id,
        body_truncated_for_url=len(body) > _MAX_BODY_IN_URL,
    )


def gmail_compose_url(draft: EmailApplyDraft) -> str:
    """Build Gmail web compose URL (login/session is the user's; JobBot does not send)."""
    body = draft.body
    if len(body) > _MAX_BODY_IN_URL:
        body = (
            body[: _MAX_BODY_IN_URL - 80]
            + "\n\n…[truncado en la URL; pegá el resto desde el dry-run de JobBot]"
        )
    return (
        "https://mail.google.com/mail/?view=cm&fs=1"
        f"&to={quote(draft.to, safe='')}"
        f"&su={quote(draft.subject, safe='')}"
        f"&body={quote(body, safe='')}"
    )


def open_gmail_compose(
    draft: EmailApplyDraft,
    *,
    opener: object | None = None,
) -> str:
    """Open Gmail compose in the browser; returns the URL opened."""
    url = gmail_compose_url(draft)
    open_fn = opener if callable(opener) else webbrowser.open
    open_fn(url)
    return url
