"""Vacantes.com landing links, sitemap locs, robots rules and JSON-LD jobs."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from html import unescape
from urllib.parse import urljoin, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup

from jobbot.models.job import JobPosting
from jobbot.portals.detect import AtsKind

ROOT = "https://vacantes.com"
_LINK = re.compile(r"^/es/vacantes/(?P<slug>.+)-(?P<hex>[0-9a-fA-F]{8})/?$")
_LOC = re.compile(r"<loc>\s*([^<\s]+)\s*</loc>", re.IGNORECASE)


@dataclass(frozen=True)
class ListingLink:
    url: str
    identifier: str
    hex_id: str


def canonical_job_url(url: str) -> str:
    """Drop the query and keep the trailing slash Vacantes uses to avoid a redirect."""
    parts = urlsplit(urljoin(ROOT, url))
    path = parts.path if parts.path.endswith("/") else f"{parts.path}/"
    return urlunsplit((parts.scheme or "https", parts.netloc or "vacantes.com", path, "", ""))


def link_from_url(url: str, *, identifier: str = "") -> ListingLink | None:
    match = _LINK.match(urlsplit(urljoin(ROOT, url)).path)
    if match is None:
        return None
    return ListingLink(
        url=canonical_job_url(url),
        identifier=identifier.strip(),
        hex_id=match.group("hex").lower(),
    )


def listing_links(html: str) -> list[ListingLink]:
    """Job links on a landing. ``data-id`` is the UUID when the page printed it."""
    soup = BeautifulSoup(html, "html.parser")
    found: list[ListingLink] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        link = link_from_url(str(anchor["href"]), identifier=str(anchor.get("data-id") or ""))
        if link is None or link.url in seen:
            continue
        seen.add(link.url)
        found.append(link)
    return found


def xml_locs(text: str) -> list[str]:
    return [unescape(item.strip()) for item in _LOC.findall(text)]


def disallowed(robots: str) -> list[str]:
    """``Disallow`` prefixes of the ``User-agent: *`` group."""
    capture = False
    found: list[str] = []
    for raw in robots.splitlines():
        line = raw.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().casefold()
        value = value.strip()
        if key == "user-agent":
            capture = value == "*"
        elif capture and key == "disallow" and value:
            found.append(value)
    return found


def path_blocked(robots: str, path: str) -> bool:
    return any(path.startswith(prefix) for prefix in disallowed(robots))


def job_from_html(html: str, *, page_url: str) -> JobPosting | None:
    """One ``JobPosting`` JSON-LD object, or ``None`` when the page has none."""
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text()
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for obj in _objects(payload):
            kind = obj.get("@type")
            types = kind if isinstance(kind, list) else [kind]
            if "JobPosting" in types:
                posting = _posting(obj, page_url)
                if posting is not None:
                    return posting
    return None


def _objects(payload: object) -> list[dict[str, object]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        graph = payload.get("@graph")
        if isinstance(graph, list):
            return [item for item in graph if isinstance(item, dict)]
        return [payload]
    return []


def _posting(obj: dict[str, object], page_url: str) -> JobPosting | None:
    title = str(obj.get("title") or "").strip()
    match = _LINK.match(urlsplit(page_url).path)
    source_id = _identifier(obj) or (match.group("hex").lower() if match else "")
    if not title or not source_id:
        return None
    org = obj.get("hiringOrganization")
    company = ""
    if isinstance(org, dict):
        company = str(org.get("name") or "").strip()
    remote = _remote(obj)
    description = _plain(str(obj.get("description") or ""))
    employment = obj.get("employmentType")
    return JobPosting(
        id="pending",
        source="vacantes",
        source_job_id=source_id,
        title=title,
        company=company or "Vacantes",
        location=_location(obj),
        remote_type="remote" if remote else None,
        employment_type=str(employment).strip() if isinstance(employment, str) else None,
        description=description,
        url=canonical_job_url(str(obj.get("url") or page_url)),
        ats_url=canonical_job_url(str(obj.get("url") or page_url)),
        ats_kind=AtsKind.VACANTES.value,
        posted_at=_aware(obj.get("datePosted")),
        closes_at=_aware(obj.get("validThrough")),
        note=_salary(obj) or None,
    )


def _identifier(obj: dict[str, object]) -> str:
    raw = obj.get("identifier")
    if isinstance(raw, dict):
        return str(raw.get("value") or "").strip()
    if isinstance(raw, str):
        return raw.strip()
    return ""


def _location(obj: dict[str, object]) -> str | None:
    raw = obj.get("jobLocation")
    if isinstance(raw, list):
        raw = raw[0] if raw else None
    if not isinstance(raw, dict):
        return None
    address = raw.get("address")
    if not isinstance(address, dict):
        return None
    parts = [
        str(address.get(key) or "").strip()
        for key in ("addressLocality", "addressRegion", "addressCountry")
    ]
    text = ", ".join(part for part in parts if part)
    return text or None


def _remote(obj: dict[str, object]) -> bool:
    kind = str(obj.get("jobLocationType") or "")
    text = f"{kind} {obj.get('jobLocation')}"
    folded = text.casefold()
    return "telecommute" in folded or "remote" in folded or "remoto" in folded


def _salary(obj: dict[str, object]) -> str:
    """There is no ``salary_text`` column; the amount is kept in ``note``."""
    raw = obj.get("baseSalary")
    if isinstance(raw, str):
        return raw.strip()
    if not isinstance(raw, dict):
        return ""
    currency = str(raw.get("currency") or "").strip()
    value = raw.get("value")
    amount = ""
    if isinstance(value, dict):
        amount = str(value.get("value") or "").strip()
    elif value is not None:
        amount = str(value).strip()
    return " ".join(part for part in (amount, currency) if part)


def _plain(html: str) -> str:
    return BeautifulSoup(html, "html.parser").get_text(" ", strip=True)


def _aware(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=ZoneInfo("UTC"))
    return parsed
