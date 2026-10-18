"""Read an Avature SearchJobs page and a JobDetail page. No network."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from bs4 import BeautifulSoup, Tag

from jobbot.models.job import JobPosting

_LEGEND = re.compile(r"(\d+)\s*-\s*(\d+)\s+of\s+(\d+)\s+results", re.I)
_JOB = re.compile(r"/JobDetail/([^/]+)/(\d+)", re.I)
_END = re.compile(r"Posting End Date\s*:?\s*(\d{1,2})-([A-Za-z]{3})-(\d{4})", re.I)
_START = re.compile(r"Posting Start Date\s*:?\s*(\d{1,2})-([A-Za-z]{3})-(\d{4})", re.I)
_TITLE = re.compile(r"Position Title\s*:?\s*(.+)", re.I)
_STATION = re.compile(r"Duty Station\(s\)\s*:?\s*(.+)", re.I)
_SENIORITY = re.compile(r"Seniority Level\s*:?\s*(.+)", re.I)
_ICS = re.compile(r"ICS Level\s*:?\s*(.+)", re.I)
_CONTRACT = re.compile(r"Contract Type\s*:?\s*(.+)", re.I)
_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
ZONE_NOTE = "zona supuesta: UTC"


@dataclass
class SearchPage:
    """One SearchJobs response."""

    jobs: list[JobPosting] = field(default_factory=list)
    page_size: int | None = None
    total: int | None = None
    has_legend: bool = False


def site_key(site_url: str) -> str:
    """`https://host/portal` → `host/portal`."""
    parts = urlsplit(site_url if "://" in site_url else f"https://{site_url}")
    path = parts.path.strip("/")
    host = parts.hostname or ""
    return f"{host}/{path}" if path else host


def canonical_job_url(url: str) -> str:
    """Drop `qtvc` and tracking parameters. Avature's robots.txt forbids `qtvc`."""
    parts = urlsplit(url)
    kept = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.casefold() != "qtvc" and not key.casefold().startswith("utm_")
    ]
    query = "&".join(f"{key}={value}" for key, value in kept)
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))


def source_job_id(site_url: str, job_url: str) -> str | None:
    """`{host}/{portal}:{id}` from the last segment of `JobDetail/{slug}/{id}`."""
    found = _JOB.search(urlsplit(job_url).path)
    if found is None:
        return None
    return f"{site_key(site_url)}:{found.group(2)}"


def company_name(site_url: str) -> str:
    """The label in the host, skipping a leading careers/jobs/www."""
    host = urlsplit(site_url if "://" in site_url else f"https://{site_url}").hostname or "avature"
    labels = [label for label in host.split(".") if label]
    if labels and labels[0] in {"careers", "jobs", "www"} and len(labels) > 2:
        return labels[1]
    return labels[0] if labels else "avature"


def parse_search(html: str, site_url: str) -> SearchPage:
    """Job cards on one SearchJobs page. Links that carry `qtvc` lose that parameter."""
    page = SearchPage()
    soup = BeautifulSoup(html or "", "html.parser")
    legend = _LEGEND.search(soup.get_text(" ", strip=True))
    if legend is not None:
        start, end, total = (int(group) for group in legend.groups())
        page.has_legend = True
        page.total = total
        if end >= start:
            page.page_size = end - start + 1
    base = site_url if "://" in site_url else f"https://{site_url}"
    parts = urlsplit(base)
    origin = f"{parts.scheme}://{parts.netloc}"
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        if not isinstance(anchor, Tag):
            continue
        href = str(anchor.get("href") or "")
        found = _JOB.search(href)
        if found is None:
            continue
        absolute = href if href.startswith("http") else origin + href
        clean = canonical_job_url(absolute)
        identity = source_job_id(base, clean)
        if identity is None or identity in seen:
            continue
        seen.add(identity)
        title = " ".join(anchor.get_text(" ", strip=True).split()) or found.group(1)
        page.jobs.append(
            JobPosting(
                id="pending",
                source="avature",
                source_job_id=identity,
                url=clean,
                ats_url=clean,
                ats_kind="avature",
                title=title[:180],
                company=company_name(base)[:180],
            )
        )
    return page


def apply_detail(job: JobPosting, html: str) -> JobPosting:
    """Fill title, place, contract and the closing moment from a JobDetail page."""
    text = BeautifulSoup(html or "", "html.parser").get_text("\n", strip=True)
    title = _line(_TITLE, text)
    station = _line(_STATION, text)
    seniority = _line(_SENIORITY, text)
    ics = _line(_ICS, text)
    contract = _line(_CONTRACT, text)
    grades = ", ".join(part for part in (seniority, ics) if part)
    closing = _moment(_END, text)
    posted = _moment(_START, text)
    remote = None
    if station and any(word in station.casefold() for word in ("home-based", "remote")):
        remote = "remote"
    return job.model_copy(
        update={
            "title": title or job.title,
            "location": station or job.location,
            "remote_type": remote or job.remote_type,
            "seniority": grades or job.seniority,
            "employment_type": contract or job.employment_type,
            "posted_at": posted or job.posted_at,
            "closes_at": closing or job.closes_at,
            "closes_on": closing.date() if closing else job.closes_on,
            "closes_text": _closing_text(text) if closing else job.closes_text,
            "note": ZONE_NOTE if closing else job.note,
            "description": text[:4000],
            "raw_description": html or job.raw_description,
        }
    )


def _closing_text(text: str) -> str | None:
    found = _END.search(text)
    return found.group(0) if found else None


def _line(pattern: re.Pattern[str], text: str) -> str | None:
    found = pattern.search(text)
    if found is None:
        return None
    cleaned = " ".join(found.group(1).split())
    return cleaned[:180] or None


def _moment(pattern: re.Pattern[str], text: str) -> datetime | None:
    found = pattern.search(text)
    if found is None:
        return None
    month = _MONTHS.get(found.group(2).casefold())
    if month is None:
        return None
    try:
        when = datetime(int(found.group(3)), month, int(found.group(1)), tzinfo=UTC)
    except ValueError:
        return None
    if pattern is _END:
        return when.replace(hour=23, minute=59, second=59)
    return when
