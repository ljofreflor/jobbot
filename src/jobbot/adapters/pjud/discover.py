"""`jobs discover --source pjud` reads the public contest grid. No login."""

from __future__ import annotations

import time
import urllib.request
from urllib.parse import urlsplit

from jobbot.adapters.pjud.parse import LISTING, parse_grid
from jobbot.companies.registry import CompanyRegistry
from jobbot.jobs.discover import (
    JobFilters,
    SiteOutcome,
    SiteStatus,
    SiteTarget,
)
from jobbot.jobs.normalization import fold_text
from jobbot.models.job import JobPosting

LOGIN_PATH = "postulacionessrh"


def pause() -> None:
    """At most one request a second. Tests replace this."""
    time.sleep(1)


def fetch_public(url: str) -> tuple[int, str, str]:
    """GET the public listing. Tests replace this. The login area is refused."""
    if LOGIN_PATH in url.casefold():
        msg = f"refusing login URL: {url}"
        raise ValueError(msg)
    pause()
    request = urllib.request.Request(url, headers={"User-Agent": "jobbot/0.1"})
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        status = int(getattr(response, "status", 200))
        body = response.read().decode("utf-8", errors="replace")
        final = str(response.geturl())
    return status, body, final


class PjudDiscover:
    """One request for the contests that are open for applications."""

    name = "pjud"
    default_details = False

    def site_target(self, raw: str) -> SiteTarget:
        if LOGIN_PATH in raw.casefold():
            msg = f"{raw} is the login area"
            raise ValueError(msg)
        text = raw if "://" in raw else f"https://{raw}"
        host = urlsplit(text).hostname or ""
        if host != "postulaciones.pjud.cl":
            msg = f"{raw} is not the contest listing"
            raise ValueError(msg)
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
        if LOGIN_PATH in target.url.casefold():
            return SiteOutcome(
                site=target.url,
                status=SiteStatus.FAILED,
                detail=f"refusing login URL: {target.url}",
            )
        try:
            status, html, _final = fetch_public(LISTING)
        except OSError as exc:
            return SiteOutcome(site=LISTING, status=SiteStatus.FAILED, detail=str(exc))
        if status != 200:
            return SiteOutcome(site=LISTING, status=SiteStatus.FAILED, detail=f"HTTP {status}")
        page = parse_grid(html)
        if page.changed:
            return SiteOutcome(site=LISTING, status=SiteStatus.CHANGED, detail=page.detail)
        kept = [job for job in page.jobs if _matches(query, job)]
        if filters is not None:
            kept = [job for job in kept if filters.keeps(job)]
        shown = kept[:limit]
        if not page.jobs:
            return SiteOutcome(site=LISTING, status=SiteStatus.EMPTY, jobs=[], feed_size=0)
        return SiteOutcome(
            site=LISTING,
            status=SiteStatus.OK,
            jobs=shown,
            feed_size=len(page.jobs),
            kept_ids=tuple(job.source_job_id or "" for job in kept),
        )


def _matches(query: str, job: JobPosting) -> bool:
    needle = fold_text(query)
    if not needle:
        return True
    blob = fold_text(f"{job.title} {job.company}")
    return needle in blob
