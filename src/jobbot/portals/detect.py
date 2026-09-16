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
    INDEED = "indeed"
    LINKEDIN = "linkedin"
    EMAIL = "email"
    UNKNOWN = "unknown"


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
    ("indeed.com", AtsKind.INDEED),
    ("linkedin.com", AtsKind.LINKEDIN),
]


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
