"""`jobs discover --source pageup` reads a public listing. `unicef` is one host."""

from __future__ import annotations

import time
import urllib.request
from urllib.parse import quote, urlsplit

from jobbot.adapters.pageup.parse import allowed, parse_listing
from jobbot.companies.registry import CompanyRegistry
from jobbot.jobs.discover import (
    JobFilters,
    SiteOutcome,
    SiteStatus,
    SiteTarget,
    registry_sites_for,
)
from jobbot.models.job import JobPosting

UNICEF_HOST = "jobs.unicef.org"


def pause() -> None:
    """At most one request a second. Tests replace this."""
    time.sleep(1)


def fetch_public(url: str) -> tuple[int, str, str]:
    """GET one public page. Tests replace this."""
    if not allowed(url):
        msg = f"robots.txt disallows {url}"
        raise ValueError(msg)
    pause()
    request = urllib.request.Request(url, headers={"User-Agent": "jobbot/0.1"})
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        status = int(getattr(response, "status", 200))
        body = response.read().decode("utf-8", errors="replace")
        final = str(response.geturl())
    return status, body, final


def listing_url(host: str, query: str) -> str:
    """Search when there is a query; otherwise the first listing page."""
    if query.strip():
        return f"https://{host}/en-us/search/?search-keyword={quote(query)}"
    return f"https://{host}/en-us/listing/"


class PageupDiscover:
    """Page a public PageUp listing. Disallowed robots paths are not requested."""

    name = "pageup"
    default_details = False
    default_host: str | None = None

    def site_target(self, raw: str) -> SiteTarget:
        text = raw.strip()
        if "://" not in text:
            text = f"https://{text}"
        parts = urlsplit(text)
        if not parts.hostname or parts.path.strip("/") or " " in raw:
            msg = f"{raw} needs a host and no path"
            raise ValueError(msg)
        return SiteTarget(url=f"https://{parts.hostname}")

    def registry_targets(self, registry: CompanyRegistry) -> list[SiteTarget]:
        found = registry_sites_for(registry, "pageup")
        if found:
            return found
        if self.default_host:
            return [SiteTarget(url=f"https://{self.default_host}")]
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
        del details
        host = urlsplit(target.url).hostname or target.url
        url: str | None = listing_url(host, query)
        jobs: list[JobPosting] = []
        seen: set[str] = set()
        first = True
        while url and len(jobs) < limit:
            if not allowed(url):
                break
            status, html, _final = fetch_public(url)
            if status != 200 and first:
                return SiteOutcome(
                    site=target.url,
                    status=SiteStatus.FAILED,
                    detail=f"HTTP {status} {url}",
                )
            if status != 200:
                break
            page = parse_listing(html, target.url, url)
            if page.captcha:
                return SiteOutcome(
                    site=target.url,
                    status=SiteStatus.FAILED,
                    detail="captcha: el listado es un desafío. Usa jobs add --file.",
                )
            if first and not page.jobs and not page.empty:
                return SiteOutcome(
                    site=target.url,
                    status=SiteStatus.CHANGED,
                    detail=f"el listado no trae avisos: {url}",
                )
            for job in page.jobs:
                identity = job.source_job_id or ""
                if identity in seen:
                    continue
                if filters is not None and not filters.keeps(job):
                    continue
                seen.add(identity)
                jobs.append(job)
                if len(jobs) >= limit:
                    break
            first = False
            url = page.next_url if len(jobs) < limit else None
        if not jobs:
            return SiteOutcome(site=target.url, status=SiteStatus.EMPTY, jobs=[])
        return SiteOutcome(site=target.url, status=SiteStatus.OK, jobs=jobs[:limit])


class UnicefDiscover(PageupDiscover):
    """UNICEF's PageUp host."""

    name = "unicef"
    default_host = UNICEF_HOST
