"""Map a Chiletrabajos listing and detail. No network."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from jobbot.jobs.normalization import fold_text
from jobbot.models.job import JobPosting

SANTIAGO = ZoneInfo("America/Santiago")
ORIGIN = "https://www.chiletrabajos.cl"
CONFIDENTIAL = "Confidencial"
_JOB = re.compile(r"/trabajo/(?P<slug>[^/?#]+)-(?P<number>\d+)/?(?:\?|$)")
_WHEN = re.compile(r"(\d{4}-\d{2}-\d{2})(?:\s+(\d{2}:\d{2}:\d{2}))?")
_BLOCKED = ("/partners", "/ofertasmuchomas")


@dataclass(frozen=True)
class ListingItem:
    """One `/trabajo/{slug}-{id}` link."""

    url: str
    title: str
    number: str
    company: str | None = None


def search_url(query: str) -> str:
    """Public search. `f=2` is what makes the text apply."""
    from urllib.parse import urlencode

    query_string = urlencode({"2": query, "f": "2"})
    return f"{ORIGIN}/encuentra-un-empleo?{query_string}"


def blocked(url: str) -> bool:
    """Paths `robots.txt` disallows for every agent."""
    path = urljoin(ORIGIN, url)
    return any(part in path for part in _BLOCKED)


def parse_listing(html: str, *, page_url: str) -> tuple[list[ListingItem], str | None]:
    """Job links, plus the page's own `rel=next` when it is allowed."""
    soup = BeautifulSoup(html or "", "html.parser")
    items: list[ListingItem] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        href = str(anchor.get("href") or "")
        if blocked(href):
            continue
        absolute = urljoin(page_url, href)
        found = _JOB.search(absolute)
        if found is None or found.group("number") in seen:
            continue
        seen.add(found.group("number"))
        company = _company_near(anchor)
        items.append(
            ListingItem(
                url=canonical(absolute) or absolute,
                title=anchor.get_text(" ", strip=True) or found.group("number"),
                number=found.group("number"),
                company=company,
            )
        )
    nxt = soup.find("a", rel="next")
    href = str(nxt.get("href") or "") if nxt is not None else ""
    if not href or blocked(href):
        return items, None
    return items, urljoin(page_url, href)


def canonical(url: str) -> str | None:
    """Drop the query. The id is the numeric suffix."""
    found = _JOB.search(url)
    if found is None:
        return None
    slug = found.group("slug")
    number = found.group("number")
    return f"{ORIGIN}/trabajo/{slug}-{number}"


def job_from_detail(html: str, *, url: str, fallback_title: str) -> JobPosting | None:
    """One detail table. Missing `Fecha` is a shape change."""
    soup = BeautifulSoup(html or "", "html.parser")
    fields = _rows(soup)
    posted = _posted(fields.get("fecha", ""))
    if posted is None:
        return None
    heading = soup.find("h1")
    title = (heading.get_text(" ", strip=True) if heading else "") or fallback_title
    employer = fields.get("buscado", "").strip()
    hidden = fold_text(employer) == "confidencial"
    company = CONFIDENTIAL if hidden or not employer else employer
    place = fields.get("ubicacion", "").strip()
    location = place or "Chile"
    remote = "remot" in fold_text(f"{title} {location}")
    body = soup.select_one("div.descripcion")
    text = body.get_text(" ", strip=True) if body else title
    return _posting(
        url=url,
        title=title,
        company=company,
        location=location,
        description=text,
        raw=str(body) if body else "",
        posted=posted,
        closes=_closes(fields.get("expira", "")),
        employment=fields.get("tipo") or None,
        remote="remote" if remote else None,
    )


def job_from_listing(item: ListingItem) -> JobPosting:
    """What the list itself showed when the detail is gone."""
    return _posting(
        url=item.url,
        title=item.title,
        company=item.company or CONFIDENTIAL,
        location="Chile",
        description=item.title,
        raw="",
        posted=None,
        closes=None,
        employment=None,
        remote=None,
    )


def _posting(
    *,
    url: str,
    title: str,
    company: str,
    location: str,
    description: str,
    raw: str,
    posted: datetime | None,
    closes: datetime | None,
    employment: str | None,
    remote: str | None,
) -> JobPosting:
    found = _JOB.search(url)
    number = found.group("number") if found else url
    return JobPosting(
        id="pending",
        source="chiletrabajos",
        source_job_id=number,
        url=canonical(url) or url,
        ats_url=canonical(url) or url,
        ats_kind="chiletrabajos",
        title=title[:180],
        company=company[:180],
        location=location[:180],
        description=description[:2000],
        raw_description=raw,
        employment_type=employment,
        remote_type=remote,
        posted_at=posted,
        closes_at=closes,
    )


def _rows(soup: BeautifulSoup) -> dict[str, str]:
    found: dict[str, str] = {}
    for cell in soup.find_all("td"):
        label = fold_text(cell.get_text(" ", strip=True))
        value = cell.find_next_sibling("td")
        if not label or value is None or label in found:
            continue
        found[label] = value.get_text(" ", strip=True)
    return found


def _company_near(anchor: object) -> str | None:
    parent = getattr(anchor, "parent", None)
    if parent is None:
        return None
    node = parent.find("span", class_="empresa")
    if node is None:
        return None
    text = node.get_text(" ", strip=True)
    return text or None


def _posted(text: str) -> datetime | None:
    found = _WHEN.search(text)
    if found is None:
        return None
    clock = found.group(2) or "00:00:00"
    try:
        moment = datetime.strptime(f"{found.group(1)} {clock}", "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return None
    return moment.replace(tzinfo=SANTIAGO)


def _closes(text: str) -> datetime | None:
    found = _WHEN.search(text)
    if found is None:
        return None
    year, month, day = (int(part) for part in found.group(1).split("-"))
    try:
        return datetime(year, month, day, 23, 59, 59, tzinfo=SANTIAGO)
    except ValueError:
        return None
