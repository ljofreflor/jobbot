"""Workday's public candidate API (CXS): search one career site, read one posting.

It is the JSON the public career page itself loads: no login, no browser. Every call
names itself (User-Agent), waits its turn per host, obeys the host's ``robots.txt``
and gives up quickly. Observed behaviour this module relies on:

- ``total`` comes only with the first page; later pages say ``0``.
- An ``offset`` past the end returns the first page again, so paging stops on repeats.
- A closed posting answers 404 or 403 with ``errorCode: S22``; that is evidence of
  closure, not a failure. A route the tenant does not know answers 406.
- ``endDate`` is when the posting leaves the site, not the closing the text announces
  (often a day or more later), so the published "Closing Date" line wins.
"""

from __future__ import annotations

import json
import logging
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any, Protocol
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from jobbot.companies.oneshot import FetchResult, RobotsPolicy, RobotsVerdict
from jobbot.jobs.career_page import ClosedPostingError
from jobbot.jobs.closing import find_closing
from jobbot.jobs.parsing import parse_job_text
from jobbot.models.job import JobPosting
from jobbot.portals.detect import AtsKind

logger = logging.getLogger("jobbot.workday")

USER_AGENT = "jobbot/0.1 (local; workday job discovery; +https://github.com/ljofreflor/jobbot)"
PAGE_SIZE = 20
MAX_LIMIT = 200
SOURCE = "workday"

_HOST = re.compile(r"^(?P<tenant>[a-z0-9][a-z0-9-]*)\.(?:wd\d+\.)?myworkdayjobs\.com$")
_LOCALE = re.compile(r"^[a-z]{2}(?:-[a-zA-Z]{2})?$")
_POSTED_DAYS = re.compile(r"(\d+)\s*\+?\s*days?\s+ago", re.I)
_JSON_HEADERS = {"Accept": "application/json", "Content-Type": "application/json"}
_WIDE_HEADERS = {"Accept": "application/json, text/plain, */*", "Content-Type": "application/json"}


class WorkdayError(RuntimeError):
    """A career site could not be read; the message names the site."""


class WorkdayRobotsDisallowed(WorkdayError):
    """The host's robots.txt does not let us read its CXS API."""


class WorkdayRefused(WorkdayError):
    """The host would not answer (403 without closure code, 429, 5xx, network)."""


class WorkdayShapeChanged(WorkdayError):
    """The JSON no longer has the fields this client reads."""


class WorkdayPostingClosed(ClosedPostingError):
    """The posting is gone: 404, 403 ``S22`` or ``canApply: false``."""


@dataclass(frozen=True)
class HttpResponse:
    status: int
    text: str = ""


class HttpRunner(Protocol):
    def __call__(
        self,
        method: str,
        url: str,
        *,
        headers: Mapping[str, str],
        body: bytes | None,
        timeout: float,
    ) -> HttpResponse: ...


def urllib_runner(
    method: str,
    url: str,
    *,
    headers: Mapping[str, str],
    body: bytes | None,
    timeout: float,
) -> HttpResponse:
    request = urllib.request.Request(url, data=body, headers=dict(headers), method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:  # noqa: S310 — public API
            return HttpResponse(int(resp.status), resp.read(2_000_000).decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        return HttpResponse(int(exc.code), exc.read(20_000).decode("utf-8", "replace"))
    except OSError as exc:
        logger.debug("Workday request failed for %s: %s", url, exc)
        return HttpResponse(0, str(exc))


def pause(seconds: float) -> None:
    time.sleep(seconds)


@dataclass(frozen=True)
class WorkdaySite:
    host: str
    tenant: str
    site: str

    @property
    def url(self) -> str:
        """Career site without locale: the form the company registry stores."""
        return f"https://{self.host}/{self.site}"

    @property
    def api(self) -> str:
        return f"https://{self.host}/wday/cxs/{self.tenant}/{self.site}"

    @property
    def label(self) -> str:
        return f"{self.tenant}/{self.site}"


@dataclass(frozen=True)
class WorkdayRef:
    site: WorkdaySite
    external_path: str

    @property
    def url(self) -> str:
        return f"{self.site.url}{self.external_path}"

    @property
    def req_id(self) -> str | None:
        return req_id_from_path(self.external_path)


def _split(url: str) -> tuple[str, str, list[str]] | None:
    parsed = urlparse(url.strip())
    host = (parsed.hostname or "").casefold()
    match = _HOST.match(host)
    if match is None:
        return None
    segments = [seg for seg in parsed.path.split("/") if seg]
    while segments and _LOCALE.match(segments[0]):
        segments = segments[1:]
    return host, match.group("tenant"), segments


def parse_site_url(url: str) -> WorkdaySite | None:
    """``https://acme.wd3.myworkdayjobs.com/en-US/External`` → host, tenant, site."""
    split = _split(url)
    if split is None:
        return None
    host, tenant, segments = split
    if not segments or segments[0] in {"job", "details", "wday"}:
        return None
    return WorkdaySite(host=host, tenant=tenant, site=segments[0])


def parse_workday_url(url: str) -> WorkdayRef | None:
    """A posting URL (with or without locale, ``/job/…`` or ``/details/…``), or None."""
    site = parse_site_url(url)
    split = _split(url)
    if site is None or split is None:
        return None
    rest = split[2][1:]
    if len(rest) < 2 or rest[0] not in {"job", "details"}:
        return None
    return WorkdayRef(site=site, external_path="/job/" + "/".join(rest[1:]))


def req_id_from_path(external_path: str) -> str | None:
    """``…/Advisor--Mental-Health_Req-05974`` → ``Req-05974`` (Workday's slug_reqId)."""
    tail = external_path.rstrip("/").rsplit("/", 1)[-1]
    if "_" not in tail:
        return None
    req = tail.rsplit("_", 1)[1].strip()
    return req or None


def source_job_id(site: WorkdaySite, req_id: str) -> str:
    """One key per vacancy and career site: the same tenant may run several sites."""
    return f"{site.label}:{req_id}"


def posted_on_date(text: str, *, today: date) -> date | None:
    """'Posted Today' / 'Posted Yesterday' / 'Posted 3 Days Ago'; '30+' stays unknown."""
    folded = (text or "").casefold()
    if "today" in folded:
        return today
    if "yesterday" in folded:
        return today - timedelta(days=1)
    if "+" in folded:
        return None
    found = _POSTED_DAYS.search(folded)
    return today - timedelta(days=int(found.group(1))) if found else None


def html_to_text(html: str) -> str:
    soup = BeautifulSoup(html or "", "html.parser")
    return soup.get_text("\n", strip=True)


@dataclass(frozen=True)
class SearchResult:
    site: WorkdaySite
    postings: list[dict[str, Any]]
    total: int
    pages: int


class _RobotsFetcher:
    def __init__(self, client: CxsClient) -> None:
        self._client = client

    def fetch(self, url: str) -> FetchResult:
        resp = self._client.request("GET", url, accept_json=False)
        return FetchResult(url=url, status=resp.status, html=resp.text)


@dataclass
class CxsClient:
    """Sequential, polite CXS reader. ``runner`` is injected so tests stay offline."""

    runner: HttpRunner | None = None
    delay: float = 1.0
    timeout: float = 10.0
    sleep: Callable[[float], None] | None = None
    clock: Callable[[], float] = time.monotonic
    requests: int = 0
    _last: dict[str, float] = field(default_factory=dict, repr=False)
    _robots: RobotsPolicy | None = field(default=None, repr=False)

    def request(
        self,
        method: str,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        accept_json: bool = True,
    ) -> HttpResponse:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"User-Agent": USER_AGENT}
        if accept_json:
            headers.update(_JSON_HEADERS)
        resp = self._send(method, url, headers, body)
        if resp.status == 406 and accept_json:
            resp = self._send(method, url, {**headers, **_WIDE_HEADERS}, body)
        return resp

    def _send(
        self, method: str, url: str, headers: Mapping[str, str], body: bytes | None
    ) -> HttpResponse:
        host = urlparse(url).netloc
        last = self._last.get(host)
        if last is not None:
            wait = self.delay - (self.clock() - last)
            if wait > 0:
                (self.sleep or pause)(wait)
        self.requests += 1
        runner = self.runner or urllib_runner
        try:
            return runner(method, url, headers=headers, body=body, timeout=self.timeout)
        finally:
            self._last[host] = self.clock()

    def check_robots(self, site: WorkdaySite) -> None:
        if self._robots is None:
            self._robots = RobotsPolicy(fetcher=_RobotsFetcher(self), user_agent=USER_AGENT)
        verdict = self._robots.verdict(f"{site.api}/jobs")
        if verdict is RobotsVerdict.DISALLOWED:
            raise WorkdayRobotsDisallowed(f"{site.label}: robots.txt disallows /wday/cxs/")
        if verdict is RobotsVerdict.HOST_REFUSED:
            raise WorkdayRefused(f"{site.label}: host refused robots.txt")

    def search(self, site: WorkdaySite, query: str, *, limit: int) -> SearchResult:
        """Page through one site's search (20 per page) until ``total`` or ``limit``."""
        self.check_robots(site)
        postings: list[dict[str, Any]] = []
        seen: set[str] = set()
        total: int | None = None
        offset = 0
        pages = 0
        while len(postings) < limit:
            body = {"appliedFacets": {}, "limit": PAGE_SIZE, "offset": offset, "searchText": query}
            resp = self.request("POST", f"{site.api}/jobs", payload=body)
            pages += 1
            payload = _json_or_error(resp, site)
            page = payload.get("jobPostings")
            if not isinstance(page, list) or (total is None and "total" not in payload):
                raise WorkdayShapeChanged(f"{site.label}: search JSON lacks jobPostings/total")
            if total is None:
                total = int(payload.get("total") or 0)
            fresh = [
                item
                for item in page
                if isinstance(item, dict) and str(item.get("externalPath") or "") not in seen
            ]
            if not fresh:
                break
            for item in fresh:
                seen.add(str(item.get("externalPath") or ""))
            postings.extend(fresh)
            offset += PAGE_SIZE
            if offset >= total or len(page) < PAGE_SIZE:
                break
        return SearchResult(site=site, postings=postings[:limit], total=total or 0, pages=pages)

    def job(self, ref: WorkdayRef) -> dict[str, Any]:
        """One posting's detail. Closure (404, 403 S22) raises ``WorkdayPostingClosed``."""
        self.check_robots(ref.site)
        resp = self.request("GET", f"{ref.site.api}{ref.external_path}")
        if resp.status in {403, 404}:
            code = _error_code(resp.text)
            if resp.status == 404 or code == "S22":
                evidence = f"HTTP {resp.status}" + (f" errorCode {code}" if code else "")
                raise WorkdayPostingClosed(f"{ref.url}: posting closed ({evidence})")
        payload = _json_or_error(resp, ref.site)
        info = payload.get("jobPostingInfo")
        if not isinstance(info, dict) or not str(info.get("title") or "").strip():
            raise WorkdayShapeChanged(f"{ref.site.label}: detail JSON lacks jobPostingInfo.title")
        return payload


def _error_code(text: str) -> str | None:
    try:
        data = json.loads(text)
    except ValueError:
        return None
    code = data.get("errorCode") if isinstance(data, dict) else None
    return str(code) if code else None


def _json_or_error(resp: HttpResponse, site: WorkdaySite) -> dict[str, Any]:
    if resp.status != 200:
        code = _error_code(resp.text)
        detail = f"HTTP {resp.status}" if resp.status else "no connection"
        if code:
            detail += f" errorCode {code}"
        raise WorkdayRefused(f"{site.label}: {detail}")
    try:
        data = json.loads(resp.text)
    except ValueError as exc:
        raise WorkdayShapeChanged(f"{site.label}: answer is not JSON") from exc
    if not isinstance(data, dict):
        raise WorkdayShapeChanged(f"{site.label}: answer is not a JSON object")
    return data


def job_from_search_item(
    site: WorkdaySite,
    item: dict[str, Any],
    *,
    company: str | None = None,
    today: date | None = None,
) -> JobPosting:
    """A search row: title, place and age. The detail adds description and closing."""
    path = str(item.get("externalPath") or "")
    ref = WorkdayRef(site=site, external_path=path)
    req = ref.req_id or _first_bullet(item) or path
    posted_text = str(item.get("postedOn") or "").strip()
    posted = posted_on_date(posted_text, today=today or datetime.now(UTC).date())
    title = str(item.get("title") or "").strip() or "Untitled"
    location = str(item.get("locationsText") or "").strip() or None
    return JobPosting(
        id="PENDING",
        source=SOURCE,
        source_job_id=source_job_id(site, req),
        url=ref.url,
        title=title,
        company=company or site.tenant,
        location=location,
        description=title,
        raw_description=title,
        ats_url=ref.url,
        ats_kind=AtsKind.WORKDAY.value,
        posted_at=_midnight(posted),
        note=f"workday: {posted_text}" if posted is None and posted_text else None,
    )


def job_from_detail(
    ref: WorkdayRef,
    payload: dict[str, Any],
    *,
    company: str | None = None,
) -> JobPosting:
    """Map a CXS detail. Raises ``WorkdayPostingClosed`` when it no longer takes applicants."""
    info: dict[str, Any] = payload.get("jobPostingInfo") or {}
    if info.get("canApply") is False:
        raise WorkdayPostingClosed(f"{ref.url}: posting closed (canApply false)")
    canonical = _canonical(ref, info)
    text = html_to_text(str(info.get("jobDescription") or ""))
    title = str(info.get("title") or "").strip()
    parsed = parse_job_text(f"{title}\n{text}", job_id="PENDING", source=SOURCE, url=canonical)
    org = payload.get("hiringOrganization")
    org_name = str(org.get("name") or "").strip() if isinstance(org, dict) else ""
    req = ref.req_id or str(info.get("jobReqId") or "").strip() or ref.external_path
    job = JobPosting(
        id="PENDING",
        source=SOURCE,
        source_job_id=source_job_id(ref.site, req),
        url=canonical,
        title=title,
        company=company or org_name or ref.site.tenant,
        location=_location(info),
        description=text,
        raw_description=str(info.get("jobDescription") or ""),
        requirements=parsed.requirements,
        skills=parsed.skills,
        seniority=parsed.seniority,
        language_requirements=parsed.language_requirements,
        employment_type=str(info.get("timeType") or "").strip() or None,
        remote_type=str(info.get("remoteType") or "").strip() or None,
        ats_url=canonical,
        ats_kind=AtsKind.WORKDAY.value,
        posted_at=_midnight(_iso_date(info.get("startDate"))),
        ats_signals=_signals(info),
    )
    closing = find_closing(text)
    if closing is not None:
        job.closes_on, job.closes_at, job.closes_text = closing.on, closing.at, closing.text
    elif (end := _iso_date(info.get("endDate"))) is not None:
        job.closes_on = end
        job.closes_text = f"endDate {end.isoformat()} (Workday: posting end, no time published)"
    return job


def _canonical(ref: WorkdayRef, info: dict[str, Any]) -> str:
    external = parse_workday_url(str(info.get("externalUrl") or ""))
    return external.url if external is not None else ref.url


def _location(info: dict[str, Any]) -> str | None:
    places = [str(info.get("location") or "").strip()]
    extra = info.get("additionalLocations")
    if isinstance(extra, list):
        places.extend(str(p).strip() for p in extra)
    unique = [p for i, p in enumerate(places) if p and p not in places[:i]]
    return "; ".join(unique) or None


def _signals(info: dict[str, Any]) -> dict[str, bool]:
    signals: dict[str, bool] = {}
    if isinstance(info.get("canApply"), bool):
        signals["can_apply"] = info["canApply"]
    if isinstance(info.get("includeResumeParsing"), bool):
        signals["resume_parsing"] = info["includeResumeParsing"]
    signals["questionnaire"] = bool(info.get("questionnaireId"))
    return signals


def _first_bullet(item: dict[str, Any]) -> str | None:
    bullets = item.get("bulletFields")
    if isinstance(bullets, list) and bullets:
        return str(bullets[0]).strip() or None
    return None


def _iso_date(raw: object) -> date | None:
    try:
        return date.fromisoformat(str(raw)[:10]) if raw else None
    except ValueError:
        return None


def _midnight(day: date | None) -> datetime | None:
    return datetime(day.year, day.month, day.day, tzinfo=UTC) if day else None


def fetch_workday_job(
    url: str,
    *,
    client: CxsClient | None = None,
    company: str | None = None,
) -> JobPosting:
    """``jobbot get`` / ``jobs add --url`` for a Workday link: live CXS detail."""
    ref = parse_workday_url(url)
    if ref is None:
        msg = f"Not a Workday posting URL (needs /<site>/job/…_<reqId>): {url}"
        raise ValueError(msg)
    reader = client or CxsClient()
    return job_from_detail(ref, reader.job(ref), company=company)
