"""UN Careers' public RSS feed and, on request, one posting's public JSON detail.

``GET https://careers.un.org/jobfeed`` is one RSS 2.0 document with every open posting:
no search parameters, no paging, no login. Each ``<item>`` carries ``title``, ``link``,
``guid`` (same as ``link``) and a ``description`` that is not the posting text but a
``<br>``-separated block of ``Key : value`` lines (Level, Job ID, Job Network, Job Family,
Department/Office, Duty Station, Staffing Exercise, Posted Date, Deadline).

Observed behaviour this module relies on (2026-10-09):

- Dates read ``10/20/2026 23:59:59 PM (New York time)``: month first, a 24-hour clock
  with a meridiem that only repeats it, and the zone in parentheses.
- ``robots.txt`` is not a file: the host answers the Angular app's HTML, so there are
  no rules. A real ``text/plain`` file with a ``Disallow`` would be obeyed.
- The detail API (``/api/public/opening/jo/{id}/en``) answers "Updated the view count
  successfully": every read adds a view to the posting, so it is opt-in.
- "Remote" in a title is not a work mode ("Remote Sensing Data Engineer"); only
  "home-based" is.
"""

from __future__ import annotations

import json
import logging
import re
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from datetime import time as clock_time
from typing import Any
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from jobbot.companies.oneshot import FetchResult, RobotsPolicy, RobotsVerdict
from jobbot.jobs.closing import zone_from_text
from jobbot.jobs.normalization import fold_text
from jobbot.jobs.parsing import parse_job_text
from jobbot.models.job import JobPosting
from jobbot.portals.detect import AtsKind

logger = logging.getLogger("jobbot.un_careers")

HOST = "careers.un.org"
FEED_URL = f"https://{HOST}/jobfeed"
DETAIL_URL = f"https://{HOST}/api/public/opening/jo/{{job_id}}/en"
USER_AGENT = "jobbot/0.1 (local; un-careers job discovery; +https://github.com/ljofreflor/jobbot)"
SOURCE = "un_careers"
MAX_FEED_BYTES = 5_000_000

_JOB_PATH = re.compile(r"/jobSearchDescription/(\d+)")
_BR = re.compile(r"<br\s*/?>", re.I)
_STAMP = re.compile(
    r"^(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(am|pm)?\s*(?:\(([^)]*)\))?",
    re.I,
)
_HOME_BASED = ("home based", "homebased")


class UnCareersError(RuntimeError):
    """The feed or a detail could not be read; the message says what happened."""


class UnCareersRobotsDisallowed(UnCareersError):
    """careers.un.org's robots.txt does not let us read this path."""


class UnCareersRefused(UnCareersError):
    """The host would not answer (non-200, 429, 5xx, network)."""


class UnCareersShapeChanged(UnCareersError):
    """The feed or the detail no longer has the structure this module reads."""


@dataclass(frozen=True)
class Answer:
    status: int
    text: str = ""
    content_type: str = ""


def _client(**kwargs: Any) -> httpx.Client:
    """Seam for tests: they pass an ``httpx.MockTransport`` and never open a socket."""
    return httpx.Client(**kwargs)


def pause(seconds: float) -> None:
    time.sleep(seconds)


class _RobotsFetcher:
    """robots.txt as ``RobotsPolicy`` expects it; an HTML page is "no rules", not a rule."""

    def __init__(self, client: UnCareersClient) -> None:
        self._client = client

    def fetch(self, url: str) -> FetchResult:
        answer = self._client.get(url, accept="text/plain")
        body = answer.text
        if "html" in answer.content_type.casefold() or body.lstrip().startswith("<"):
            body = ""
        return FetchResult(url=url, status=answer.status, html=body)


@dataclass
class UnCareersClient:
    """Sequential, polite reader: honest User-Agent, 1 request/s, 10 s timeout, robots.txt."""

    transport: httpx.BaseTransport | None = None
    delay: float = 1.0
    timeout: float = 10.0
    sleep: Callable[[float], None] | None = None
    clock: Callable[[], float] = time.monotonic
    requests: int = 0
    _last: float | None = field(default=None, repr=False)
    _robots: RobotsPolicy | None = field(default=None, repr=False)
    _feed: list[FeedItem] | None = field(default=None, repr=False)

    def get(self, url: str, *, accept: str) -> Answer:
        if self._last is not None:
            wait = self.delay - (self.clock() - self._last)
            if wait > 0:
                (self.sleep or pause)(wait)
        self.requests += 1
        headers = {"User-Agent": USER_AGENT, "Accept": accept}
        try:
            with _client(
                transport=self.transport,
                timeout=self.timeout,
                headers=headers,
                follow_redirects=True,
            ) as client:
                resp = client.get(url)
                text = resp.content[:MAX_FEED_BYTES].decode("utf-8", "replace")
                return Answer(resp.status_code, text, resp.headers.get("content-type", ""))
        except httpx.HTTPError as exc:
            logger.debug("UN Careers request failed for %s: %s", url, exc)
            return Answer(0, str(exc))
        finally:
            self._last = self.clock()

    def check_robots(self, url: str) -> None:
        if self._robots is None:
            self._robots = RobotsPolicy(fetcher=_RobotsFetcher(self), user_agent=USER_AGENT)
        verdict = self._robots.verdict(url)
        path = urlparse(url).path
        if verdict is RobotsVerdict.DISALLOWED:
            raise UnCareersRobotsDisallowed(f"{HOST}: robots.txt disallows {path}")
        if verdict is RobotsVerdict.HOST_REFUSED:
            raise UnCareersRefused(f"{HOST}: host refused robots.txt")

    def feed(self) -> list[FeedItem]:
        """Every open posting, read once per client (several queries share one request)."""
        if self._feed is None:
            self.check_robots(FEED_URL)
            answer = self.get(FEED_URL, accept="application/rss+xml, application/xml, text/xml")
            if answer.status != 200:
                detail = f"HTTP {answer.status}" if answer.status else "no connection"
                raise UnCareersRefused(f"{FEED_URL}: {detail}")
            self._feed = parse_feed(answer.text)
        return self._feed

    def detail(self, job_id: str) -> dict[str, Any]:
        """One posting's JSON detail (adds one view to it on the site)."""
        url = DETAIL_URL.format(job_id=job_id)
        self.check_robots(url)
        answer = self.get(url, accept="application/json")
        if answer.status != 200:
            detail = f"HTTP {answer.status}" if answer.status else "no connection"
            raise UnCareersRefused(f"detalle {job_id}: {detail}")
        try:
            payload = json.loads(answer.text)
        except ValueError as exc:
            raise UnCareersShapeChanged(f"detalle {job_id}: answer is not JSON") from exc
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, dict) or not str(data.get("jobTitle") or "").strip():
            raise UnCareersShapeChanged(f"detalle {job_id}: JSON lacks data.jobTitle")
        return data


@dataclass(frozen=True)
class FeedItem:
    job_id: str
    title: str
    meta: dict[str, str]

    @property
    def url(self) -> str:
        return canonical_url(self.job_id)

    def value(self, key: str) -> str:
        value = self.meta.get(key, "").strip()
        return "" if value.casefold() == "undefined" else value

    def matches(self, query: str) -> bool:
        """Every word of the query, folded, inside title, family, network or office."""
        words = fold_text(query).split()
        keys = ("Job Family", "Job Network", "Department/Office")
        haystack = fold_text(" ".join([self.title, *(self.value(k) for k in keys)]))
        return all(word in haystack for word in words)


def canonical_url(job_id: str) -> str:
    return f"https://{HOST}/jobSearchDescription/{job_id}?language=en"


def job_id_from_url(url: str) -> str | None:
    """``…/jobSearchDescription/286047?language=en`` → ``286047``."""
    parsed = urlparse((url or "").strip())
    if (parsed.hostname or "").casefold() != HOST:
        return None
    found = _JOB_PATH.search(parsed.path)
    return found.group(1) if found else None


def parse_meta(description: str) -> dict[str, str]:
    """``Level : P-3 <br> Job ID : 286047 <br> …`` → ``{"Level": "P-3", …}``."""
    meta: dict[str, str] = {}
    for part in _BR.split(description or ""):
        key, sep, value = part.partition(":")
        if sep and key.strip():
            meta[key.strip()] = " ".join(value.split())
    return meta


def parse_feed(xml_text: str) -> list[FeedItem]:
    """Every ``<item>``; raises ``UnCareersShapeChanged`` naming what is missing."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise UnCareersShapeChanged(f"{FEED_URL}: answer is not XML ({exc})") from exc
    channel = root.find("channel") if root.tag == "rss" else None
    if channel is None:
        raise UnCareersShapeChanged(f"{FEED_URL}: no <rss><channel> (got <{root.tag}>)")
    items: list[FeedItem] = []
    for node in channel.findall("item"):
        title = " ".join((node.findtext("title") or "").split())
        meta = parse_meta(node.findtext("description") or "")
        link = node.findtext("guid") or node.findtext("link") or ""
        digits = "".join(ch for ch in meta.get("Job ID", "") if ch.isdigit())
        job_id = job_id_from_url(link) or digits
        if not job_id:
            raise UnCareersShapeChanged(
                f"{FEED_URL}: item {title[:60]!r} has no Job ID nor a jobSearchDescription guid"
            )
        items.append(FeedItem(job_id=job_id, title=title or "Untitled", meta=meta))
    if items and not any("Duty Station" in i.meta or "Deadline" in i.meta for i in items):
        raise UnCareersShapeChanged(f"{FEED_URL}: item descriptions lack Duty Station/Deadline")
    return items


def parse_stamp(raw: str) -> tuple[date, datetime | None] | None:
    """``10/20/2026 23:59:59 PM (New York time)`` → the date, and the moment when zoned.

    The meridiem only matters for a 12-hour clock (``11:59:59 PM``); with the feed's
    24-hour clock it agrees with the hour, so both readings give the same moment.
    """
    found = _STAMP.match((raw or "").strip())
    if found is None:
        return None
    month, day, year, hour, minute = (int(found.group(i)) for i in range(1, 6))
    second = int(found.group(6) or 0)
    meridiem = (found.group(7) or "").casefold()
    if meridiem == "pm" and hour < 12:
        hour += 12
    elif meridiem == "am" and hour == 12:
        hour = 0
    try:
        on = date(year, month, day)
        moment = clock_time(hour, minute, second)
    except ValueError:
        return None
    zone = zone_from_text(fold_text(found.group(8) or ""))
    return on, datetime.combine(on, moment, tzinfo=zone) if zone is not None else None


def is_home_based(*texts: str) -> bool:
    folded = " ".join(fold_text(t) for t in texts)
    return any(word in folded for word in _HOME_BASED)


def employment_type(level: str) -> str | None:
    if not level:
        return None
    if level.upper() == "CON":
        return "consultancy"
    if level.upper().startswith("I-"):
        return "internship"
    return "staff"


def organization(department: str) -> str:
    """The entity: first segment of ``UNRWA - Programme Education - Lebanon``."""
    return department.split(" - ", 1)[0].strip() or "United Nations"


_META_ORDER = (
    "Department/Office",
    "Duty Station",
    "Level",
    "Job Network",
    "Job Family",
    "Posted Date",
    "Deadline",
    "Job ID",
)


def job_from_item(item: FeedItem) -> JobPosting:
    """One feed item as a posting: metadata only (``--details`` adds the text)."""
    level = item.value("Level")
    station = item.value("Duty Station")
    department = item.value("Department/Office")
    lines = [item.title, *(f"{k}: {item.value(k)}" for k in _META_ORDER if item.value(k))]
    text = "\n".join(lines)
    job = JobPosting(
        id="PENDING",
        source=SOURCE,
        source_job_id=item.job_id,
        url=item.url,
        title=item.title,
        company=organization(department),
        location=station or None,
        description=text,
        raw_description=text,
        seniority=level or None,
        employment_type=employment_type(level),
        remote_type="remote" if is_home_based(station, item.title) else None,
        ats_url=item.url,
        ats_kind=AtsKind.UN_CAREERS.value,
    )
    posted = parse_stamp(item.value("Posted Date"))
    if posted is not None:
        job.posted_at = posted[1] or datetime.combine(posted[0], clock_time(), tzinfo=UTC)
    deadline = item.value("Deadline")
    closing = parse_stamp(deadline)
    if closing is not None:
        job.closes_on, job.closes_at = closing
        job.closes_text = f"Deadline: {deadline}"
    return job


def with_detail(job: JobPosting, data: dict[str, Any]) -> JobPosting:
    """The feed row plus the posting text; the detail's ``endDate`` (UTC) wins on conflict."""
    html = str(data.get("jobDescription") or "")
    text = BeautifulSoup(html, "html.parser").get_text("\n", strip=True)
    parsed = parse_job_text(f"{job.title}\n{text}", job_id="PENDING", source=SOURCE, url=job.url)
    full = job.model_copy(
        update={
            "description": f"{job.description}\n\n{text}" if text else job.description,
            "raw_description": html or job.raw_description,
            "requirements": parsed.requirements,
            "skills": parsed.skills,
            "language_requirements": parsed.language_requirements,
        }
    )
    end = _utc(data.get("endDate"))
    if end is not None and (job.closes_at is None or job.closes_at != end):
        if job.closes_at is not None:
            full.note = (
                f"un_careers: Deadline del feed {job.closes_at.isoformat()} ≠ endDate del "
                f"detalle {end.isoformat()}; se usa el detalle"
            )
        local = end.astimezone(job.closes_at.tzinfo) if job.closes_at is not None else end
        full.closes_at, full.closes_on = local, local.date()
        full.closes_text = f"endDate {data.get('endDate')} (detalle UN Careers, UTC)"
    if full.posted_at is None:
        full.posted_at = _utc(data.get("startDate"))
    return full


def _utc(raw: object) -> datetime | None:
    if not raw:
        return None
    try:
        moment = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)
