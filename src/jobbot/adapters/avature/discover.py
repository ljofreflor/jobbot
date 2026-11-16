"""`jobs discover --source avature` reads a public SearchJobs list. `unops` is one site."""

from __future__ import annotations

import time
import urllib.request
from http.client import HTTPMessage
from typing import IO
from urllib.parse import quote, urlsplit

from jobbot.adapters.avature.parse import apply_detail, parse_search
from jobbot.companies.registry import CompanyRegistry
from jobbot.jobs.discover import (
    JobFilters,
    SiteOutcome,
    SiteStatus,
    SiteTarget,
    registry_sites_for,
)
from jobbot.models.job import JobPosting

UNOPS_SITE = "https://careers.unops.org/careersmarketplace"


def pause() -> None:
    """At most one request a second. Tests replace this."""
    time.sleep(1)


class QtvcDisallowed(ValueError):
    """The URL carries the session parameter robots.txt disallows, so it is not requested."""


class _NoQtvcRedirect(urllib.request.HTTPRedirectHandler):
    """Avature 302s a clean link onto `qtvc=`; that hop is refused before it is requested."""

    def redirect_request(  # noqa: PLR0913
        self,
        req: urllib.request.Request,
        fp: IO[bytes],
        code: int,
        msg: str,
        headers: HTTPMessage,
        newurl: str,
    ) -> urllib.request.Request | None:
        if blocked_qtvc(newurl):
            reason = f"refusing qtvc redirect: {newurl}"
            raise QtvcDisallowed(reason)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def fetch_public(url: str) -> tuple[int, str, str]:
    """GET one public page. Tests replace this. Never requests a `qtvc` URL, redirects included."""
    if blocked_qtvc(url):
        msg = f"refusing qtvc URL: {url}"
        raise QtvcDisallowed(msg)
    pause()
    request = urllib.request.Request(url, headers={"User-Agent": "jobbot/0.1"})  # noqa: S310
    with urllib.request.build_opener(_NoQtvcRedirect).open(request, timeout=30) as response:
        status = int(getattr(response, "status", 200))
        body = response.read().decode("utf-8", errors="replace")
        final = str(response.geturl())
    if blocked_qtvc(final):
        msg = f"refusing qtvc URL: {final}"
        raise QtvcDisallowed(msg)
    return status, body, final


def fetch_detail(job: JobPosting) -> JobPosting:
    """Read one JobDetail page. A link or a hop into `qtvc` leaves the posting as it was."""
    if not job.url or blocked_qtvc(job.url):
        return job
    try:
        status, html, _final = fetch_public(job.url)
    except QtvcDisallowed:
        return job
    return apply_detail(job, html) if status == 200 else job


def search_url(site_url: str, query: str, offset: int) -> str:
    """`GET {site}/SearchJobs/?search=&jobOffset=`."""
    base = site_url.rstrip("/")
    return f"{base}/SearchJobs/?search={quote(query)}&jobOffset={offset}"


class AvatureDiscover:
    """Page a public Avature portal. The session parameter `qtvc` is never requested."""

    name = "avature"
    default_details = False
    default_site: str | None = None

    def site_target(self, raw: str) -> SiteTarget:
        text = raw.strip()
        if "://" not in text:
            text = f"https://{text}"
        parts = urlsplit(text)
        portal = parts.path.strip("/")
        if not parts.hostname or not portal or " " in raw:
            msg = f"{raw} needs a host and a portal path"
            raise ValueError(msg)
        url = f"https://{parts.hostname}/{portal.split('/')[0]}"
        return SiteTarget(url=url)

    def registry_targets(self, registry: CompanyRegistry) -> list[SiteTarget]:
        found = registry_sites_for(registry, "avature")
        if found:
            return found
        if self.default_site:
            return [SiteTarget(url=self.default_site)]
        return []

    def discover_site(
        self,
        target: SiteTarget,
        *,
        query: str,
        limit: int,
        details: bool,
        filters: JobFilters | None = None,
    ) -> SiteOutcome:
        jobs: list[JobPosting] = []
        seen: set[str] = set()
        offset = 0
        total: int | None = None
        # A card carries title and link only: --location / --level live on the JobDetail page.
        read_details = details or (filters is not None and filters.active)
        while len(jobs) < limit:
            url = search_url(target.url, query, offset)
            try:
                status, html, _final = fetch_public(url)
            except QtvcDisallowed as exc:
                if jobs:
                    break
                return SiteOutcome(site=target.url, status=SiteStatus.ROBOTS, detail=str(exc))
            if status != 200:
                if offset == 0:
                    return SiteOutcome(
                        site=target.url,
                        status=SiteStatus.FAILED,
                        detail=f"HTTP {status} {url}",
                    )
                break
            page = parse_search(html, target.url)
            if offset == 0 and not page.has_legend and not page.jobs:
                return SiteOutcome(
                    site=target.url,
                    status=SiteStatus.CHANGED,
                    detail=f"el listado no trae resultados ni JobDetail: {url}",
                )
            if not page.jobs:
                break
            fresh = 0
            for job in page.jobs:
                identity = job.source_job_id or ""
                if identity in seen:
                    continue
                seen.add(identity)
                fresh += 1
                if read_details:
                    job = fetch_detail(job)
                if filters is not None and not filters.keeps(job):
                    continue
                jobs.append(job)
                if len(jobs) >= limit:
                    break
            if not fresh:
                # The host served a page we already read: `jobOffset` wrapped around.
                break
            total = page.total if page.total is not None else total
            step = page.page_size or len(page.jobs)
            offset += step
            if total is not None and offset >= total:
                break
            if page.page_size is not None and len(page.jobs) < page.page_size:
                break
        if not jobs:
            return SiteOutcome(site=target.url, status=SiteStatus.EMPTY, jobs=[])
        return SiteOutcome(site=target.url, status=SiteStatus.OK, jobs=jobs[:limit])


class UnopsDiscover(AvatureDiscover):
    """The UNOPS marketplace, as one Avature site."""

    name = "unops"
    default_site = UNOPS_SITE


def blocked_qtvc(url: str) -> bool:
    """True when the URL carries the session parameter robots.txt disallows."""
    return "qtvc=" in url.casefold()
