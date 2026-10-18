"""Read a PageUp listing. No network."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup, Tag

from jobbot.jobs.normalization import fold_text
from jobbot.models.job import JobPosting

_JOB = re.compile(r"/en-us/job/(\d+)", re.I)
# Longer prefixes first so `/ciuat` is not confused with a shorter neighbour.
_BLOCKED = (
    "/uatinternal",
    "/testint",
    "/staging",
    "/cwuat",
    "/ciuat",
    "/awake",
    "/admin",
    "/uat",
    "/ci",
)


@dataclass
class ListingPage:
    """One listing or search response."""

    jobs: list[JobPosting]
    next_url: str | None
    empty: bool
    captcha: bool


def site_host(site_url: str) -> str:
    """Host only, without a scheme."""
    text = site_url if "://" in site_url else f"https://{site_url}"
    return urlsplit(text).hostname or site_url


def company_name(site_url: str) -> str:
    """The label in the host, skipping a leading jobs/careers/www."""
    labels = [label for label in site_host(site_url).split(".") if label]
    if labels and labels[0] in {"jobs", "careers", "www"} and len(labels) > 2:
        return labels[1]
    return labels[0] if labels else "pageup"


def allowed(url: str) -> bool:
    """False for the paths PageUp's robots.txt disallows."""
    path = urlsplit(url).path.casefold()
    return not any(path == prefix or path.startswith(prefix + "/") for prefix in _BLOCKED)


def canonical_job_url(site_url: str, href: str) -> tuple[str, str] | None:
    """`https://{host}/en-us/job/{id}/` and `{host}:{id}`."""
    found = _JOB.search(href)
    if found is None:
        return None
    host = site_host(site_url)
    job_id = found.group(1)
    return f"https://{host}/en-us/job/{job_id}/", f"{host}:{job_id}"


def parse_listing(html: str, site_url: str, page_url: str) -> ListingPage:
    """Job cards, the next page, and whether the page is empty or a challenge."""
    soup = BeautifulSoup(html or "", "html.parser")
    jobs: list[JobPosting] = []
    seen: set[str] = set()
    host = site_host(site_url)
    origin = f"https://{host}"
    for card in soup.select("div.list-view--item"):
        if not isinstance(card, Tag):
            continue
        link = card.select_one("a.job-link")
        if not isinstance(link, Tag):
            continue
        href = str(link.get("href") or "")
        mapped = canonical_job_url(origin, href)
        if mapped is None or mapped[1] in seen:
            continue
        url, identity = mapped
        seen.add(identity)
        title = " ".join(link.get_text(" ", strip=True).split()) or identity
        place = card.select_one("span.location")
        location = None
        if isinstance(place, Tag):
            location = " ".join(place.get_text(" ", strip=True).split()) or None
        teaser = card.select_one("div.row--teaser")
        summary = teaser.get_text(" ", strip=True) if isinstance(teaser, Tag) else ""
        remote = _remote(title, href, location)
        jobs.append(
            JobPosting(
                id="pending",
                source="pageup",
                source_job_id=identity,
                url=url,
                ats_url=url,
                ats_kind="pageup",
                title=title[:180],
                company=company_name(origin)[:180],
                location=location or None,
                remote_type=remote,
                description=summary[:2000],
                closes_at=_closing(card),
            )
        )
    more = soup.select_one("a.more-link")
    next_url = None
    if isinstance(more, Tag) and more.get("href"):
        next_url = urljoin(page_url, str(more.get("href")))
    text = soup.get_text(" ", strip=True).casefold()
    captcha = "g-recaptcha" in (html or "").casefold() and not jobs
    empty = not jobs and not captcha and "no results" in text
    return ListingPage(jobs=jobs, next_url=next_url, empty=empty, captcha=captcha)


def _remote(title: str, href: str, location: str | None) -> str | None:
    """Home-based is a work mode wherever it reads; "Remote" only as a place.

    A title like "Remote Sensing Data Engineer" names a field, not a work mode.
    """
    place = fold_text(location or "")
    if "home based" in fold_text(f"{title} {href} {location or ''}"):
        return "remote"
    return "remote" if "remote" in place.split() else None


def _closing(card: Tag) -> datetime | None:
    node = card.select_one("span.close-date time")
    if not isinstance(node, Tag):
        return None
    raw = str(node.get("datetime") or "").strip()
    if not raw:
        return None
    try:
        moment = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        return None
    return moment
