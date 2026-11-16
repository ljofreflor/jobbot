"""`jobs discover --source chiletrabajos` reads the public HTML search."""

from __future__ import annotations

import time
import urllib.request
from urllib.parse import urlsplit

from jobbot.adapters.chiletrabajos.parse import (
    ListingItem,
    blocked,
    job_from_detail,
    job_from_listing,
    parse_listing,
    search_url,
)
from jobbot.companies.registry import CompanyRegistry
from jobbot.jobs.discover import JobFilters, SiteOutcome, SiteStatus, SiteTarget
from jobbot.jobs.normalization import fold_text
from jobbot.models.job import JobPosting

LISTING = "https://www.chiletrabajos.cl/encuentra-un-empleo"
USER_AGENT = "jobbot/0.1"
_EMPTY = ("no se encontraron", "sin resultados", "0 empleos")


def pause() -> None:
    """At most one request a second. Tests replace this."""
    time.sleep(1)


def fetch_public(url: str) -> tuple[int, str, str]:
    """GET one public page. Tests replace this. Disallowed paths are refused."""
    if blocked(url):
        msg = f"robots.txt disallows {url}"
        raise ValueError(msg)
    pause()
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        status = int(getattr(response, "status", 200))
        body = response.read().decode("utf-8", errors="replace")
        final = str(response.geturl())
    return status, body, final


class ChiletrabajosDiscover:
    """Read the public search, then each detail. A 404 keeps the list row."""

    name = "chiletrabajos"
    default_details = True

    def site_target(self, raw: str) -> SiteTarget:
        host = (urlsplit(raw if "://" in raw else f"https://{raw}").hostname or "").lower()
        if host not in {"chiletrabajos.cl", "www.chiletrabajos.cl"}:
            raise ValueError(f"{raw} is not chiletrabajos.cl")
        return SiteTarget(url=LISTING)

    def registry_targets(self, registry: CompanyRegistry) -> list[SiteTarget]:
        del registry
        return [SiteTarget(url=LISTING)]

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
        text = query.strip()
        if not text:
            return SiteOutcome(
                site=target.url,
                status=SiteStatus.FAILED,
                detail="chiletrabajos needs a query",
            )
        filters = filters or JobFilters()
        jobs: list[JobPosting] = []
        seen: set[str] = set()
        seen_pages: set[str] = set()
        page: str | None = search_url(text)
        while page and len(jobs) < limit:
            if page in seen_pages or blocked(page):
                break
            seen_pages.add(page)
            status, body, final = fetch_public(page)
            if status != 200:
                return SiteOutcome(
                    site=target.url,
                    status=SiteStatus.FAILED,
                    detail=f"HTTP {status}",
                )
            items, nxt = parse_listing(body, page_url=final or page)
            if not items:
                if jobs:
                    break
                if "g-recaptcha" in body.casefold():
                    return SiteOutcome(
                        site=target.url,
                        status=SiteStatus.FAILED,
                        detail="captcha: jobs add --file",
                    )
                folded = fold_text(body)
                if any(phrase in folded for phrase in _EMPTY):
                    return SiteOutcome(
                        site=target.url,
                        status=SiteStatus.EMPTY,
                        detail="0 resultados",
                    )
                return SiteOutcome(
                    site=target.url,
                    status=SiteStatus.CHANGED,
                    detail=f"el listado ya no trae /trabajo/: {page}",
                )
            for item in items:
                if len(jobs) >= limit or item.number in seen:
                    continue
                seen.add(item.number)
                job, problem = _detail(item)
                if problem:
                    changed = problem.startswith("la ficha")
                    return SiteOutcome(
                        site=target.url,
                        status=SiteStatus.CHANGED if changed else SiteStatus.FAILED,
                        detail=problem,
                    )
                if job is not None and filters.keeps(job):
                    jobs.append(job)
            page = nxt if len(jobs) < limit else None
        return SiteOutcome(site=target.url, status=SiteStatus.OK, jobs=jobs[:limit])


def _detail(item: ListingItem) -> tuple[JobPosting | None, str]:
    status, body, _final = fetch_public(item.url)
    if status == 404:
        return job_from_listing(item), ""
    if status != 200:
        return None, f"HTTP {status}"
    parsed = job_from_detail(body, url=item.url, fallback_title=item.title)
    if parsed is None:
        return None, f"la ficha no trae Fecha: {item.url}"
    return parsed, ""
