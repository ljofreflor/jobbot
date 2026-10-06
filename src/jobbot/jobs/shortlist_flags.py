"""Flags for ``jobs shortlist``: expired / closing soon — never invent a date (#205)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from jobbot.jobs.closure import closure_evidence
from jobbot.models.job import JobPosting

# Explicit calendar date only (YYYY-MM-DD or YYYY/MM/DD). No "in 3 days", no TZ guess.
_ISO_DATE = re.compile(
    r"(?i)\b(?:closes?|deadline|cierre|hasta|closing\s+date|fecha\s+de\s+cierre)"
    r"\s*[:=\-]?\s*(\d{4})[-/](\d{2})[-/](\d{2})\b"
)

DEFAULT_URGENT_DAYS = 7


@dataclass(frozen=True)
class ShortlistFlags:
    """What shortlist can say without inventing a close date."""

    expired: str | None = None  # closure phrase, or "deadline passed: YYYY-MM-DD"
    urgent: str | None = None  # "closes YYYY-MM-DD" when within the window

    @property
    def labels(self) -> tuple[str, ...]:
        out: list[str] = []
        if self.expired:
            out.append("expired")
        if self.urgent and not self.expired:
            out.append("urgent")
        return tuple(out)


def parse_closes_on(text: str) -> date | None:
    """Return a calendar close date only when the posting states YYYY-MM-DD unambiguously."""
    if not text:
        return None
    match = _ISO_DATE.search(text)
    if match is None:
        return None
    try:
        return date(int(match.group(1)), int(match.group(2)), int(match.group(3)))
    except ValueError:
        return None


def shortlist_flags(
    job: JobPosting,
    *,
    today: date | None = None,
    urgent_days: int = DEFAULT_URGENT_DAYS,
) -> ShortlistFlags:
    """Offline flags from stored text. Ambiguous TZ/relative phrases → no flag."""
    blob = "\n".join(part for part in (job.description, job.raw_description) if part)
    closed = closure_evidence(blob)
    closes = parse_closes_on(blob)
    day = today or datetime.now(UTC).date()
    expired: str | None = closed
    urgent: str | None = None
    if closes is not None:
        if closes < day:
            expired = expired or f"deadline passed: {closes.isoformat()}"
        elif closes <= day + timedelta(days=max(0, urgent_days)):
            urgent = f"closes {closes.isoformat()}"
    return ShortlistFlags(expired=expired, urgent=urgent)
