"""ATS / recruitment portal detection and kinds."""

from __future__ import annotations

import re
from enum import StrEnum
from urllib.parse import urlparse


class AtsKind(StrEnum):
    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    WORKDAY = "workday"
    ASHBY = "ashby"
    GETONBOARD = "getonboard"
    SMARTRECRUITERS = "smartrecruiters"
    BAMBOOHR = "bamboohr"
    SUCCESSFACTORS = "successfactors"
    ORACLE = "oracle"
    TEAMTAILOR = "teamtailor"
    WORKABLE = "workable"
    RECRUITEE = "recruitee"
    TORRE = "torre"
    INDEED = "indeed"
    LINKEDIN = "linkedin"
    EMAIL = "email"
    UNKNOWN = "unknown"


# Boards/aggregators: many companies publish there, so they never identify one employer.
JOB_BOARD_KINDS: frozenset[AtsKind] = frozenset(
    {AtsKind.INDEED, AtsKind.LINKEDIN, AtsKind.GETONBOARD, AtsKind.TORRE}
)


# Host suffix / substring → kind (checked in order)
_HOST_RULES: list[tuple[str, AtsKind]] = [
    ("greenhouse.io", AtsKind.GREENHOUSE),
    ("boards.greenhouse.io", AtsKind.GREENHOUSE),
    ("jobs.lever.co", AtsKind.LEVER),
    ("lever.co", AtsKind.LEVER),
    ("myworkdayjobs.com", AtsKind.WORKDAY),
    ("workday.com", AtsKind.WORKDAY),
    ("ashbyhq.com", AtsKind.ASHBY),
    ("jobs.ashbyhq.com", AtsKind.ASHBY),
    ("getonbrd.com", AtsKind.GETONBOARD),
    ("getonboard.com", AtsKind.GETONBOARD),
    ("smartrecruiters.com", AtsKind.SMARTRECRUITERS),
    ("bamboohr.com", AtsKind.BAMBOOHR),
    ("successfactors.com", AtsKind.SUCCESSFACTORS),
    ("successfactors.eu", AtsKind.SUCCESSFACTORS),
    ("sapsf.com", AtsKind.SUCCESSFACTORS),
    ("sapsf.eu", AtsKind.SUCCESSFACTORS),
    ("taleo.net", AtsKind.ORACLE),
    ("oraclecloud.com", AtsKind.ORACLE),
    ("teamtailor.com", AtsKind.TEAMTAILOR),
    ("workable.com", AtsKind.WORKABLE),
    ("recruitee.com", AtsKind.RECRUITEE),
    ("torre.ai", AtsKind.TORRE),
    ("torre.co", AtsKind.TORRE),
    ("indeed.com", AtsKind.INDEED),
    ("linkedin.com", AtsKind.LINKEDIN),
]

# Embedded markers that prove an ATS behind a corporate page (technical evidence only).
_HTML_MARKERS: tuple[tuple[re.Pattern[str], AtsKind, str], ...] = (
    (
        re.compile(r"(?:boards|job-boards)\.greenhouse\.io/embed", re.I),
        AtsKind.GREENHOUSE,
        "greenhouse embed script",
    ),
    (
        re.compile(r"(?:boards|job-boards)\.greenhouse\.io/[a-z0-9_-]+", re.I),
        AtsKind.GREENHOUSE,
        "greenhouse board link",
    ),
    (re.compile(r"jobs\.lever\.co/[a-z0-9_-]+", re.I), AtsKind.LEVER, "lever board link"),
    (
        re.compile(r"[a-z0-9_-]+\.wd\d+\.myworkdayjobs\.com", re.I),
        AtsKind.WORKDAY,
        "workday tenant host",
    ),
    (re.compile(r"jobs\.ashbyhq\.com/[a-z0-9_-]+", re.I), AtsKind.ASHBY, "ashby board link"),
    (
        re.compile(r"(?:careers|jobs)\.smartrecruiters\.com/[a-z0-9_-]+", re.I),
        AtsKind.SMARTRECRUITERS,
        "smartrecruiters board link",
    ),
    (re.compile(r"[a-z0-9_-]+\.teamtailor\.com", re.I), AtsKind.TEAMTAILOR, "teamtailor host"),
    (
        re.compile(r"(?:apply|[a-z0-9_-]+)\.workable\.com", re.I),
        AtsKind.WORKABLE,
        "workable host",
    ),
    (re.compile(r"[a-z0-9_-]+\.recruitee\.com", re.I), AtsKind.RECRUITEE, "recruitee host"),
    (
        re.compile(r"[a-z0-9_-]*\.(?:successfactors|sapsf)\.(?:com|eu)", re.I),
        AtsKind.SUCCESSFACTORS,
        "successfactors host",
    ),
    (
        re.compile(r"[a-z0-9_-]+\.(?:taleo\.net|fa\.oraclecloud\.com)", re.I),
        AtsKind.ORACLE,
        "oracle/taleo host",
    ),
    (re.compile(r"[a-z0-9_-]+\.bamboohr\.com", re.I), AtsKind.BAMBOOHR, "bamboohr host"),
)


def detect_ats(url: str) -> AtsKind:
    """Classify a recruitment URL by host (facts only; no login)."""
    raw = url.strip()
    if not raw:
        return AtsKind.UNKNOWN
    if raw.lower().startswith("mailto:"):
        return AtsKind.EMAIL
    if not re.match(r"^https?://", raw, re.I):
        raw = "https://" + raw
    host = (urlparse(raw).hostname or "").lower()
    if not host:
        return AtsKind.UNKNOWN
    for needle, kind in _HOST_RULES:
        if host == needle or host.endswith("." + needle) or needle in host:
            return kind
    return AtsKind.UNKNOWN


def detect_ats_in_html(html: str) -> tuple[AtsKind, str]:
    """Classify by embedded ATS markers. Returns (kind, evidence); never guesses by looks."""
    if not html:
        return AtsKind.UNKNOWN, ""
    for pattern, kind, label in _HTML_MARKERS:
        match = pattern.search(html)
        if match:
            return kind, f"html marker: {label} ({match.group(0)[:60]})"
    return AtsKind.UNKNOWN, ""


def extract_http_urls(text: str) -> list[str]:
    """Pull http(s) URLs from free text / post body."""
    pattern = re.compile(r"https?://[^\s<>\"')\]]+", re.I)
    out: list[str] = []
    seen: set[str] = set()
    for match in pattern.finditer(text or ""):
        url = match.group(0).rstrip(".,;:)")
        if url not in seen:
            seen.add(url)
            out.append(url)
    return out


def first_external_ats_url(urls: list[str]) -> tuple[str | None, AtsKind]:
    """Prefer non-LinkedIn ATS / board links from a post (incl. unknown hosts)."""
    ranked: list[tuple[str, AtsKind]] = []
    for url in urls:
        kind = detect_ats(url)
        if kind == AtsKind.LINKEDIN:
            continue
        host = (urlparse(url if "://" in url else f"https://{url}").hostname or "").lower()
        if host.endswith("lnkd.in") or host == "lnkd.in":
            continue
        ranked.append((url, kind))
    for url, kind in ranked:
        if kind not in {AtsKind.UNKNOWN, AtsKind.INDEED}:
            return url, kind
    for url, kind in ranked:
        if kind != AtsKind.INDEED:
            return url, kind
    return None, AtsKind.UNKNOWN
