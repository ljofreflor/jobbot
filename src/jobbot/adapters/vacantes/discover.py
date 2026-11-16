"""`jobs discover --source vacantes` reads a landing or the vacancy sitemap."""

from __future__ import annotations

import time
import urllib.request
from urllib.parse import urlsplit

from jobbot.adapters.vacantes.parse import (
    ROOT,
    ListingLink,
    job_from_html,
    link_from_url,
    listing_links,
    path_blocked,
    xml_locs,
)
from jobbot.companies.registry import CompanyRegistry
from jobbot.jobs.discover import JobFilters, SiteOutcome, SiteStatus, SiteTarget
from jobbot.jobs.normalization import fold_text
from jobbot.models.job import JobPosting

USER_AGENT = "jobbot/0.1"
ROBOTS_URL = f"{ROOT}/robots.txt"
SITEMAP_URL = f"{ROOT}/sitemap.xml"
LANDINGS = {"CL": f"{ROOT}/es/empleo/empleos-en-chile/"}


def pause() -> None:
    """At most one request a second. Tests replace this."""
    time.sleep(1)


def fetch_public(url: str) -> tuple[int, str]:
    """GET one public page. Tests replace this. Query strings and ``/api/`` are refused."""
    parts = urlsplit(url)
    if parts.query or "/api/" in parts.path:
        msg = f"vacantes does not request {url}"
        raise ValueError(msg)
    pause()
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        status = int(getattr(response, "status", 200))
        body = response.read().decode("utf-8", errors="replace")
    return status, body


class VacantesDiscover:
    name = "vacantes"
    default_details = True

    def __init__(self) -> None:
        self.country = "CL"
        self.all_sitemap = False
        self.known_ids: set[str] = set()

    def site_target(self, raw: str) -> SiteTarget:
        host = (urlsplit(raw).hostname or "").removeprefix("www.")
        if host != "vacantes.com":
            msg = "vacantes reads https://vacantes.com"
            raise ValueError(msg)
        return SiteTarget(url=ROOT)

    def registry_targets(self, registry: CompanyRegistry) -> list[SiteTarget]:
        del registry
        return [SiteTarget(url=ROOT)]

    def discover_site(
        self,
        target: SiteTarget,
        *,
        query: str,
        limit: int,
        details: bool,
        filters: JobFilters | None = None,
    ) -> SiteOutcome:
        del target, details
        status, robots = _read(ROBOTS_URL)
        if status is None:
            return _failed(query, robots)
        if status != 200:
            return _failed(query, f"robots.txt HTTP {status}")
        if self.all_sitemap:
            if path_blocked(robots, "/es/vacantes/"):
                return _blocked(query, "/es/vacantes/")
            links = self._sitemap_links(query)
            if isinstance(links, SiteOutcome):
                return links
        else:
            landing = LANDINGS[self.country]
            path = urlsplit(landing).path
            if path_blocked(robots, path):
                return _blocked(query, path)
            status, body = _read(landing)
            if status is None:
                return _failed(query, body)
            if status != 200:
                return _failed(query, f"landing HTTP {status}")
            links = listing_links(body)
        jobs, missed, fetched = self._details(links, limit, filters)
        if fetched and missed == fetched and not jobs:
            return SiteOutcome(
                site=ROOT,
                status=SiteStatus.CHANGED,
                detail="detail 200 without JobPosting JSON-LD",
            )
        if not links:
            return SiteOutcome(site=ROOT, status=SiteStatus.EMPTY, detail="0 avisos")
        return SiteOutcome(site=ROOT, status=SiteStatus.OK, jobs=jobs)

    def _sitemap_links(self, query: str) -> list[ListingLink] | SiteOutcome:
        status, body = _read(SITEMAP_URL)
        if status is None:
            return _failed(query, body)
        if status != 200:
            return _failed(query, f"sitemap HTTP {status}")
        vacancy = next((loc for loc in xml_locs(body) if "sitemap-vacancies" in loc), "")
        if not vacancy or "?" in vacancy:
            return SiteOutcome(
                site=ROOT,
                status=SiteStatus.CHANGED,
                detail="sitemap has no vacancy list",
            )
        status, listing = _read(vacancy)
        if status is None:
            return _failed(query, listing)
        if status != 200:
            return _failed(query, f"sitemap HTTP {status}")
        needle = fold_text(query)
        links: list[ListingLink] = []
        for loc in xml_locs(listing):
            if "?" in loc or "/api/" in loc:
                continue
            link = link_from_url(loc)
            if link is None:
                continue
            if needle and needle not in fold_text(urlsplit(link.url).path):
                continue
            links.append(link)
        return links

    def _details(
        self,
        links: list[ListingLink],
        limit: int,
        filters: JobFilters | None,
    ) -> tuple[list[JobPosting], int, int]:
        jobs: list[JobPosting] = []
        missed = 0
        fetched = 0
        for link in links:
            if len(jobs) >= limit:
                break
            if link.identifier in self.known_ids or link.hex_id in self.known_ids:
                continue
            status, body = _read(link.url)
            fetched += 1
            if status != 200:
                continue
            job = job_from_html(body, page_url=link.url)
            if job is None:
                missed += 1
                continue
            if job.source_job_id in self.known_ids:
                continue
            if filters is not None and not filters.keeps(job):
                continue
            jobs.append(job)
        return jobs, missed, fetched


def _read(url: str) -> tuple[int | None, str]:
    try:
        return fetch_public(url)
    except (OSError, ValueError) as exc:
        return None, str(exc)


def _failed(query: str, detail: str) -> SiteOutcome:
    del query
    return SiteOutcome(site=ROOT, status=SiteStatus.FAILED, detail=detail)


def _blocked(query: str, path: str) -> SiteOutcome:
    return _failed(query, f"robots.txt disallows {path}. Use jobs add --file.")
