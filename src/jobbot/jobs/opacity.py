"""How illegible a posting is, from evidence already on disk. No network.

The fit score stays. These signals only say whether the employer side is readable.

Weights, each added and then capped at 1:

- freshness ``stale`` (older than ``max_age_days``): 0.30
- freshness ``unknown`` (no date): 0.10
- ``repost`` (same ATS URL, or same company and title, on another id): 0.25
- portal not known (host absent, or present only as ``unknown``): 0.20
- ``silence`` (latest local event is prepared/applied and older than N days): 0.25

Closure is not a weight. A filled or expired banner is ``closed`` and the shortlist
ranks it after every posting that is not closed. Bands: score < 0.25 ``clear``,
< 0.55 ``murky``, otherwise ``opaque``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlparse

from jobbot.jobs.closure import closure_evidence
from jobbot.jobs.freshness import DEFAULT_MAX_AGE_DAYS, age_in_days
from jobbot.jobs.normalization import fold_text
from jobbot.models.job import JobPosting

_WEIGHT_STALE = 0.30
_WEIGHT_UNDATED = 0.10
_WEIGHT_REPOST = 0.25
_WEIGHT_UNKNOWN_PORTAL = 0.20
_WEIGHT_SILENCE = 0.25
_CLEAR_BELOW = 0.25
_MURKY_BELOW = 0.55
DEFAULT_SILENCE_DAYS = 30
_WAITING = frozenset({"prepared", "applied"})


@dataclass(frozen=True)
class Opacity:
    """One posting's employer-side signals."""

    freshness: str
    closure: str
    repost: bool
    portal_known: bool
    silence: str
    score: float
    band: str

    def label(self) -> str:
        """Shortlist tag: band plus the flags that made it less readable."""
        parts = [self.band]
        if self.closure == "closed":
            parts.append("closed")
        if self.freshness == "stale":
            parts.append("stale")
        if self.repost:
            parts.append("repost")
        if not self.portal_known:
            parts.append("portal?")
        if self.silence == "silent":
            parts.append("silent")
        return " ".join(parts)


def closure_of(job: JobPosting) -> str:
    """``closed`` from a filled/expired phrase or a stored closed status; else open or unknown."""
    if closure_evidence(job.description) or closure_evidence(job.raw_description or ""):
        return "closed"
    status = (job.open_status or "").casefold()
    if status == "open":
        return "open"
    if status == "closed":
        return "closed"
    return "unknown"


def freshness_band(
    posted_at: datetime | None,
    *,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    now: datetime | None = None,
) -> str:
    """``fresh``, ``stale``, or ``unknown`` when the posting has no date."""
    if max_age_days <= 0:
        return "fresh"
    days = age_in_days(posted_at, now=now)
    if days is None:
        return "unknown"
    if days <= max_age_days:
        return "fresh"
    return "stale"


def ats_identity(url: str | None) -> str | None:
    """Host + path, without query or fragment. Mailto and host-less strings are ignored."""
    if not url or url.casefold().startswith("mailto:"):
        return None
    raw = url if "://" in url else f"https://{url}"
    parsed = urlparse(raw)
    host = (parsed.hostname or "").casefold().removeprefix("www.")
    if not host:
        return None
    return f"{host}{parsed.path.rstrip('/')}"


def repost_ids(jobs: list[JobPosting]) -> set[str]:
    """Ids that share an ATS URL, or the same company and title, with another id."""
    by_url: dict[str, list[str]] = {}
    by_name: dict[str, list[str]] = {}
    for job in jobs:
        by_name.setdefault(f"{fold_text(job.company)}\n{fold_text(job.title)}", []).append(job.id)
        key = ats_identity(job.ats_url)
        if key:
            by_url.setdefault(key, []).append(job.id)
    flagged: set[str] = set()
    for group in (*by_url.values(), *by_name.values()):
        if len(group) > 1:
            flagged.update(group)
    return flagged


def portal_known(job: JobPosting, sites: list[tuple[str, str]]) -> bool:
    """True when the posting host matches a site whose ATS is not ``unknown``.

    ``sites`` is ``(domain, ats)`` already limited to evidenced rows.
    """
    hosts = {h for h in (ats_identity(job.ats_url), ats_identity(job.url)) if h}
    hosts = {item.split("/", 1)[0] for item in hosts}
    for domain, ats in sites:
        if not ats or ats == "unknown":
            continue
        site = domain.casefold().removeprefix("www.")
        if not site:
            continue
        for host in hosts:
            if host == site or host.endswith("." + site):
                return True
    return False


def silence_of(
    events: list[tuple[str, str | None, datetime]],
    *,
    now: datetime,
    after_days: int = DEFAULT_SILENCE_DAYS,
) -> str:
    """``silent`` when the latest event is still prepared/applied past N days; else ``n/a``."""
    if not events:
        return "n/a"
    _kind, detail, moment = max(events, key=lambda item: item[2])
    status = (detail or _kind or "").casefold()
    if status not in _WAITING:
        return "n/a"
    days = age_in_days(moment, now=now)
    if days is not None and days > after_days:
        return "silent"
    return "n/a"


def opacity_score(
    *,
    freshness: str,
    repost: bool,
    portal_known: bool,
    silence: str,
) -> float:
    """Composite in ``[0, 1]``. Closure is excluded; it only changes sort order."""
    score = 0.0
    if freshness == "stale":
        score += _WEIGHT_STALE
    elif freshness == "unknown":
        score += _WEIGHT_UNDATED
    if repost:
        score += _WEIGHT_REPOST
    if not portal_known:
        score += _WEIGHT_UNKNOWN_PORTAL
    if silence == "silent":
        score += _WEIGHT_SILENCE
    return min(score, 1.0)


def band_for(score: float) -> str:
    if score < _CLEAR_BELOW:
        return "clear"
    if score < _MURKY_BELOW:
        return "murky"
    return "opaque"


def shortlist_key(*, closed: bool, band: str, fit: float) -> tuple[int, int, float]:
    """Closed last, then clearer bands, then higher fit."""
    order = {"clear": 0, "murky": 1, "opaque": 2}
    return (1 if closed else 0, order.get(band, 2), -fit)


def assess(
    job: JobPosting,
    *,
    peers: list[JobPosting],
    sites: list[tuple[str, str]],
    events: list[tuple[str, str | None, datetime]],
    now: datetime,
    max_age_days: int = DEFAULT_MAX_AGE_DAYS,
    silence_days: int = DEFAULT_SILENCE_DAYS,
) -> Opacity:
    """Signals for one posting. Reads only the arguments; it does not fetch."""
    freshness = freshness_band(job.posted_at, max_age_days=max_age_days, now=now)
    closure = closure_of(job)
    repost = job.id in repost_ids(peers)
    known = portal_known(job, sites)
    silence = silence_of(events, now=now, after_days=silence_days)
    score = opacity_score(
        freshness=freshness,
        repost=repost,
        portal_known=known,
        silence=silence,
    )
    return Opacity(
        freshness=freshness,
        closure=closure,
        repost=repost,
        portal_known=known,
        silence=silence,
        score=score,
        band=band_for(score),
    )
