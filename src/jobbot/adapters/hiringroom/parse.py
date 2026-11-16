"""Saved HiringRoom vacancy. The listing's second page has no known endpoint."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from jobbot.models.job import JobPosting
from jobbot.portals.detect import AtsKind

_VACANCY_ID = re.compile(r"/jobs/get_vacancy/([0-9a-fA-F]{24})")
_AGO = re.compile(r"hace\s+(\d+)\s+d[ií]as?", re.IGNORECASE)
_SHARED = frozenset({"www", "hiringroom"})


class HiringRoomParseError(ValueError):
    """The saved page has no vacancy title."""


def listing_links(html: str, *, base: str) -> list[str]:
    """Canonical vacancy URLs already present in a saved listing page."""
    soup = BeautifulSoup(html or "", "html.parser")
    found: list[str] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "")
        if _VACANCY_ID.search(href) is None:
            continue
        absolute = urljoin(base, href.split("?", 1)[0])
        if absolute not in seen:
            seen.add(absolute)
            found.append(absolute)
    return found


def parse_vacancy(html: str, *, url: str, today: date) -> JobPosting:
    """Offline vacancy: title, place, description and a relative posting day."""
    soup = BeautifulSoup(html or "", "html.parser")
    title_node = soup.select_one(".vacancy-name")
    title = title_node.get_text(" ", strip=True) if title_node is not None else ""
    if not title:
        raise HiringRoomParseError("saved HiringRoom vacancy has no vacancy-name")

    place_node = soup.select_one(".hero__information-vacancy")
    location = place_node.get_text(" ", strip=True) if place_node is not None else ""
    if location == title:
        location = ""
    body = soup.select_one(".job-description-content")
    description = body.get_text("\n", strip=True) if body is not None else ""
    when = soup.select_one(".hero__time-vacancy")
    posted = _posted_at(when.get_text(" ", strip=True) if when is not None else "", today=today)
    vacancy_id = _id_from(url)
    company = _company(url)
    return JobPosting(
        id="pending",
        source=AtsKind.HIRINGROOM.value,
        source_job_id=f"{company}:{vacancy_id}" if vacancy_id else None,
        url=_canonical(url),
        title=title,
        company=company,
        location=location or None,
        description=description,
        raw_description=description,
        ats_url=_canonical(url),
        ats_kind=AtsKind.HIRINGROOM.value,
        posted_at=posted,
    )


def _posted_at(text: str, *, today: date) -> datetime | None:
    found = _AGO.search(text or "")
    if found is None:
        return None
    when = today - timedelta(days=int(found.group(1)))
    return datetime(when.year, when.month, when.day, tzinfo=UTC)


def _id_from(url: str) -> str:
    found = _VACANCY_ID.search(urlsplit(url).path)
    return found.group(1).lower() if found else ""


def _company(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    label = host.split(".")[0] if host.endswith(".hiringroom.com") else ""
    if label and label not in _SHARED:
        return label
    return "HiringRoom"


def _canonical(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}{parts.path}"
