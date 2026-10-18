"""`jobs discover --source avature` reads a public SearchJobs list. `unops` is one site."""

from __future__ import annotations

import time
import urllib.request
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


def fetch_public(url: str) -> tuple[int, str, str]:
    """GET one public page. Tests replace this. Never called with `qtvc`."""
    if "qtvc=" in url.casefold():
        msg = f"refusing qtvc URL: {url}"
        raise ValueError(msg)
    pause()
    request = urllib.request.Request(url, headers={"User-Agent": "jobbot/0.1"})
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        status = int(getattr(response, "status", 200))
        body = response.read().decode("utf-8", errors="replace")
        final = str(response.geturl())
    return status, body, final


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
        while len(jobs) < limit:
            url = search_url(target.url, query, offset)
            status, html, final = fetch_public(url)
            if "qtvc=" in final.casefold():
                break
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
            for job in page.jobs:
                identity = job.source_job_id or ""
                if identity in seen:
                    continue
                if details and job.url and "qtvc=" not in job.url.casefold():
                    detail_status, detail_html, _final = fetch_public(job.url)
                    if detail_status == 200:
                        job = apply_detail(job, detail_html)
                if filters is not None and not filters.keeps(job):
                    continue
                seen.add(identity)
                jobs.append(job)
                if len(jobs) >= limit:
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
