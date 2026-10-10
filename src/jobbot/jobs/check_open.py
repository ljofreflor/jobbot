"""Is a stored posting still open? Ask its source again, read-only — or say unknown.

Three answers, each with the evidence behind it:

- ``open``: the source says it takes applicants. Only Workday's CXS can say so today
  (``canApply`` and ``posted``, and no published closing already past).
- ``closed``: the source says it stopped — 404/410, a closing phrase on the page,
  ``canApply: false``, Workday's 403 ``S22``, or a published closing that has passed.
- ``unknown``: anything else. A 403, a login wall, a page without a closing phrase, a
  robots.txt that forbids reading or a dropped connection: none of them is evidence
  that the posting is open, and none that it closed.

Every request names itself, obeys ``robots.txt``, waits its turn per host and gives
up quickly. Sites behind a login (LinkedIn) are not read at all.
"""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta
from typing import Any
from urllib.parse import urlparse

from jobbot.adapters.workday import cxs
from jobbot.adapters.workday.cxs import (
    CxsClient,
    HttpResponse,
    HttpRunner,
    WorkdayError,
    WorkdayPostingClosed,
    WorkdayRef,
    WorkdayRobotsDisallowed,
    job_from_detail,
    parse_workday_url,
)
from jobbot.companies.oneshot import FetchResult, RobotsPolicy, RobotsVerdict
from jobbot.companies.urls import request_url
from jobbot.jobs import closing as closing_clock
from jobbot.jobs.closing import ClosingState, closing_state, find_closing
from jobbot.jobs.closure import closure_evidence, visible_soup
from jobbot.jobs.open_signals import (
    TRABAJANDO_API,
    OpenStatus,
    Signal,
    is_chiletrabajos,
    read_chiletrabajos,
    read_trabajando,
    trabajando_offer_id,
)
from jobbot.models.job import JobPosting

USER_AGENT = "jobbot/0.1 (local; posting status check; +https://github.com/ljofreflor/jobbot)"
RECHECK_AFTER = timedelta(hours=24)
_HTML_HEADERS = {"Accept": "text/html,application/xhtml+xml"}
_JSON_HEADERS = {"Accept": "application/json"}
_GONE = frozenset({404, 410})
# Hosts whose postings only show to a signed-in member; no CDP reader exists for them.
_LOGIN_HOSTS = ("linkedin.com", "lnkd.in")
_PARENTHESIS = re.compile(r"\(([^()]*)\)\s*$")


__all__ = ["OpenStatus", "request_url"]

Closes = tuple[date | None, datetime | None, str | None]


@dataclass(frozen=True)
class OpenCheck:
    job_id: str
    url: str | None
    status: OpenStatus
    evidence: str
    checked_at: datetime
    method: str
    closes_on: date | None = None
    closes_at: datetime | None = None
    closes_text: str | None = None

    @property
    def closes(self) -> Closes | None:
        """The closing the source published now, when it published one."""
        if self.closes_on is None:
            return None
        return self.closes_on, self.closes_at, self.closes_text

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "url": self.url,
            "status": self.status.value,
            "reason": self.evidence,
            "evidence": self.evidence,
            "checked_at": self.checked_at.isoformat(),
            "method": self.method,
            "closes_on": self.closes_on.isoformat() if self.closes_on else None,
            "closes_at": self.closes_at.isoformat() if self.closes_at else None,
        }


@dataclass
class PoliteHttp:
    """Sequential GET with a pause per host. ``runner`` is injected so tests stay offline."""

    runner: HttpRunner | None = None
    delay: float = 1.0
    timeout: float = 10.0
    sleep: Callable[[float], None] | None = None
    clock: Callable[[], float] = time.monotonic
    requests: int = 0
    _last: dict[str, float] = field(default_factory=dict, repr=False)

    def get(self, url: str, headers: Mapping[str, str] | None = None) -> HttpResponse:
        url = request_url(url)
        host = urlparse(url).netloc
        last = self._last.get(host)
        if last is not None:
            wait = self.delay - (self.clock() - last)
            if wait > 0:
                (self.sleep or cxs.pause)(wait)
        self.requests += 1
        runner = self.runner or cxs.urllib_runner
        sent = {"User-Agent": USER_AGENT, **(headers or {})}
        try:
            return runner("GET", url, headers=sent, body=None, timeout=self.timeout)
        finally:
            self._last[host] = self.clock()

    def fetch(self, url: str) -> FetchResult:
        """``Fetcher`` for ``RobotsPolicy``: robots.txt rides the same pause."""
        resp = self.get(url)
        return FetchResult(url=url, status=resp.status, html=resp.text)


def posting_url(job: JobPosting) -> str | None:
    """Where the posting takes applicants: the ATS link first, then the stored URL."""
    for candidate in (job.ats_url, job.url):
        if candidate and candidate.strip():
            return candidate.strip()
    return None


def due_for_check(
    job: JobPosting, *, now: datetime, recheck_after: timedelta = RECHECK_AFTER
) -> bool:
    """``--all`` skips postings already found closed less than a day ago."""
    if job.open_status != OpenStatus.CLOSED or job.checked_at is None:
        return True
    checked = job.checked_at if job.checked_at.tzinfo else job.checked_at.replace(tzinfo=UTC)
    return now - checked >= recheck_after


def is_verified_closed(job: JobPosting) -> bool:
    return job.open_status == OpenStatus.CLOSED


def verification_label(job: JobPosting) -> str:
    """``cerrado, verificado 2026-10-09: HTTP 404`` for the shortlist; empty when never checked."""
    if not job.open_status or job.checked_at is None:
        return ""
    names = {OpenStatus.OPEN: "abierto", OpenStatus.CLOSED: "cerrado"}
    name = names.get(OpenStatus(job.open_status), "vigencia desconocida")
    label = f"{name}, verificado {job.checked_at.date().isoformat()}"
    return f"{label}: {job.open_evidence}" if job.open_evidence else label


@dataclass
class OpenChecker:
    """Classifies one stored posting per call. Network pieces are injectable."""

    http: PoliteHttp = field(default_factory=PoliteHttp)
    workday: CxsClient | None = None
    now: Callable[[], datetime] | None = None
    _robots: RobotsPolicy | None = field(default=None, repr=False)

    def check(self, job: JobPosting) -> OpenCheck:
        """Never raises: a posting that cannot be checked is ``unknown`` with the error."""
        moment = (self.now or closing_clock.utc_now)()
        stored = posting_url(job)
        try:
            result = self._classify(job, stored, moment)
        except Exception as exc:  # noqa: BLE001 — one posting must not stop `--all`
            evidence = f"error al verificar: {type(exc).__name__}: {exc}"
            result = _result(job, stored, OpenStatus.UNKNOWN, evidence, moment)
        result = replace(result, url=stored)
        if result.status is OpenStatus.UNKNOWN:
            return _stored_closing_or(result, job, moment)
        return result

    def _classify(self, job: JobPosting, stored: str | None, moment: datetime) -> OpenCheck:
        if stored is None:
            return _result(job, None, OpenStatus.UNKNOWN, "sin URL para verificar", moment)
        try:
            web = urlparse(stored).scheme in {"http", "https"}
            url = request_url(stored) if web else ""
        except ValueError as exc:
            return _result(job, stored, OpenStatus.UNKNOWN, f"URL inválida: {exc}", moment)
        if not web:
            evidence = "no es una página web (sin verificación)"
            return _result(job, stored, OpenStatus.UNKNOWN, evidence, moment)
        if (ref := parse_workday_url(url)) is not None:
            return self._workday(job, ref, moment)
        if (offer := trabajando_offer_id(url)) is not None:
            return self._trabajando(job, offer, moment)
        return self._http(job, url, moment)

    def _readable(self, job: JobPosting, url: str, moment: datetime) -> OpenCheck | None:
        """None when robots.txt lets us read ``url``; otherwise the ``unknown`` it causes."""
        if self._robots is None:
            self._robots = RobotsPolicy(fetcher=self.http, user_agent=USER_AGENT)
        verdict = self._robots.verdict(url)
        if verdict is RobotsVerdict.DISALLOWED:
            evidence = "robots.txt no permite leer la página"
            return _result(job, url, OpenStatus.UNKNOWN, evidence, moment)
        if verdict is RobotsVerdict.HOST_REFUSED:
            evidence = "el sitio rechazó leer robots.txt"
            return _result(job, url, OpenStatus.UNKNOWN, evidence, moment)
        return None

    def _trabajando(self, job: JobPosting, offer: str, moment: datetime) -> OpenCheck:
        api = TRABAJANDO_API.format(offer_id=offer)
        if (blocked := self._readable(job, api, moment)) is not None:
            return blocked
        resp = self.http.get(api, _JSON_HEADERS)
        if resp.status in _GONE:
            return _result(job, api, OpenStatus.CLOSED, f"HTTP {resp.status}", moment, "trabajando")
        if resp.status != 200:
            evidence = f"Trabajando: HTTP {resp.status}" if resp.status else "sin conexión"
            return _result(job, api, OpenStatus.UNKNOWN, evidence, moment, "trabajando")
        try:
            payload = json.loads(resp.text)
        except ValueError:
            evidence = "Trabajando: la respuesta no es JSON"
            return _result(job, api, OpenStatus.UNKNOWN, evidence, moment, "trabajando")
        return _from_signal(job, api, read_trabajando(payload, now=moment), moment, "trabajando")

    def _workday(self, job: JobPosting, ref: WorkdayRef, moment: datetime) -> OpenCheck:
        url = ref.url
        client = self.workday or CxsClient(runner=self.http.runner, sleep=self.http.sleep)
        self.workday = client
        try:
            payload = client.job(ref)
        except WorkdayPostingClosed as exc:
            return _result(job, url, OpenStatus.CLOSED, _parenthesis(str(exc)), moment, "workday")
        except WorkdayRobotsDisallowed:
            evidence = "robots.txt no permite leer la API CXS"
            return _result(job, url, OpenStatus.UNKNOWN, evidence, moment, "workday")
        except WorkdayError as exc:
            return _result(job, url, OpenStatus.UNKNOWN, str(exc), moment, "workday")
        info: dict[str, Any] = payload.get("jobPostingInfo") or {}
        try:
            detail = job_from_detail(ref, payload)
        except WorkdayPostingClosed:
            return _result(job, url, OpenStatus.CLOSED, "canApply: false", moment, "workday")
        closes = (detail.closes_on, detail.closes_at, detail.closes_text)
        if info.get("posted") is False:
            evidence = "posted: false"
            return _result(job, url, OpenStatus.CLOSED, evidence, moment, "workday", closes)
        state = closing_state(detail.closes_at, detail.closes_on, now=moment)
        if state is ClosingState.EXPIRED:
            evidence = f"cierre vencido: {detail.closes_text or detail.closes_on}"
            return _result(job, url, OpenStatus.CLOSED, evidence, moment, "workday", closes)
        if info.get("canApply") is True:
            evidence = "canApply: true" + (", posted: true" if info.get("posted") else "")
            return _result(job, url, OpenStatus.OPEN, evidence, moment, "workday", closes)
        evidence = "CXS no informa canApply"
        return _result(job, url, OpenStatus.UNKNOWN, evidence, moment, "workday", closes)

    def _http(self, job: JobPosting, url: str, moment: datetime) -> OpenCheck:
        parsed = urlparse(url)
        host = (parsed.hostname or "").casefold()
        unknown = OpenStatus.UNKNOWN
        if any(host == h or host.endswith("." + h) for h in _LOGIN_HOSTS):
            evidence = "LinkedIn exige sesión; check-open no lee LinkedIn"
            return _result(job, url, unknown, evidence, moment)
        if parsed.path.casefold().endswith(".pdf"):
            return _result(job, url, unknown, "PDF: sin señal de vigencia en línea", moment)
        if (blocked := self._readable(job, url, moment)) is not None:
            return blocked
        resp = self.http.get(url, _HTML_HEADERS)
        if resp.status in _GONE:
            return _result(job, url, OpenStatus.CLOSED, f"HTTP {resp.status}", moment, "http")
        if resp.status == 0:
            return _result(job, url, unknown, "sin conexión", moment, "http")
        if not 200 <= resp.status < 300:
            evidence = f"HTTP {resp.status}: el sitio no respondió el aviso"
            return _result(job, url, unknown, evidence, moment, "http")
        phrase = closure_evidence(resp.text)
        if phrase:
            return _result(job, url, OpenStatus.CLOSED, f"«{phrase}»", moment, "http")
        if is_chiletrabajos(url) and (signal := read_chiletrabajos(resp.text, now=moment)):
            return _from_signal(job, url, signal, moment, "chiletrabajos")
        published = find_closing(visible_soup(resp.text).get_text("\n", strip=True))
        if published is not None:
            state = closing_state(published.at, published.on, now=moment)
            if state is ClosingState.EXPIRED:
                evidence = f"cierre publicado vencido: {published.text}"
                return _result(job, url, OpenStatus.CLOSED, evidence, moment, "http")
        evidence = f"HTTP {resp.status} sin señal de cierre (no implica abierto)"
        return _result(job, url, unknown, evidence, moment, "http")


def _result(
    job: JobPosting,
    url: str | None,
    status: OpenStatus,
    evidence: str,
    moment: datetime,
    method: str = "none",
    closes: Closes | None = None,
) -> OpenCheck:
    """``closes`` is the closing the source publishes now (on, at, text); it is kept."""
    on, at, text = closes or (None, None, None)
    return OpenCheck(
        job_id=job.id,
        url=url,
        status=status,
        evidence=evidence,
        checked_at=moment,
        method=method,
        closes_on=on,
        closes_at=at,
        closes_text=text,
    )


def _from_signal(
    job: JobPosting, url: str, signal: Signal, moment: datetime, method: str
) -> OpenCheck:
    closes: Closes | None = None
    if signal.closes_on is not None:
        closes = (signal.closes_on, None, signal.evidence)
    return _result(job, url, signal.status, signal.evidence, moment, method, closes)


def _stored_closing_or(result: OpenCheck, job: JobPosting, moment: datetime) -> OpenCheck:
    """The source said nothing, but the closing stored with the posting already passed."""
    if closing_state(job.closes_at, job.closes_on, now=moment) is not ClosingState.EXPIRED:
        return result
    stored = job.closes_text or (job.closes_on.isoformat() if job.closes_on else "")
    evidence = f"cierre guardado vencido: {stored} ({result.evidence})"
    return OpenCheck(
        job_id=result.job_id,
        url=result.url,
        status=OpenStatus.CLOSED,
        evidence=evidence,
        checked_at=result.checked_at,
        method=result.method,
    )


def _parenthesis(message: str) -> str:
    found = _PARENTHESIS.search(message)
    return found.group(1) if found else message
