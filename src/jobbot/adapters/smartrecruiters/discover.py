"""`jobs discover --source smartrecruiters` reads the public Posting API."""

from __future__ import annotations

import json
import time
import urllib.request
from urllib.parse import quote, urlencode

from jobbot.adapters.smartrecruiters.parse import (
    PAGE_SIZE,
    board_in_text,
    company_identifier,
    parse_postings,
)
from jobbot.companies.registry import CompanyRegistry
from jobbot.jobs.discover import (
    JobFilters,
    SiteOutcome,
    SiteStatus,
    SiteTarget,
    registry_sites_for,
)
from jobbot.jobs.geo import normalize_country
from jobbot.models.job import JobPosting


def pause() -> None:
    """At most one request a second. Tests replace this."""
    time.sleep(1)


def fetch_public(url: str) -> tuple[int, str, str]:
    """GET one public API page. Tests replace this."""
    pause()
    request = urllib.request.Request(url, headers={"User-Agent": "jobbot/0.1"})
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        status = int(getattr(response, "status", 200))
        body = response.read().decode("utf-8", errors="replace")
        final = str(response.geturl())
    return status, body, final


def postings_url(company_id: str, query: str, offset: int, country: str) -> str:
    """`GET /v1/companies/{id}/postings` with country, query and offset."""
    params: dict[str, str] = {"offset": str(offset), "limit": str(PAGE_SIZE)}
    if country:
        params["country"] = country.lower()
    if query.strip():
        params["q"] = query
    query_string = urlencode(params)
    return (
        f"https://api.smartrecruiters.com/v1/companies/{quote(company_id)}/postings?{query_string}"
    )


class SmartRecruitersDiscover:
    """Page a public board. A 404 is this board's failure; the caller tries the next."""

    name = "smartrecruiters"
    default_details = False
    countries: tuple[str, ...] = ("CL",)

    def site_target(self, raw: str) -> SiteTarget:
        ident = company_identifier(raw)
        if not ident or " " in ident:
            msg = f"{raw} needs a company identifier"
            raise ValueError(msg)
        return SiteTarget(url=f"https://jobs.smartrecruiters.com/{ident}", company=ident)

    def registry_targets(self, registry: CompanyRegistry) -> list[SiteTarget]:
        found: list[SiteTarget] = []
        seen: set[str] = set()
        for site in registry_sites_for(registry, "smartrecruiters"):
            ident = company_identifier(site.url) or _board_from_evidence(registry, site.url)
            if ident and ident not in seen:
                seen.add(ident)
                found.append(
                    SiteTarget(url=f"https://jobs.smartrecruiters.com/{ident}", company=ident)
                )
        return found

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
        ident = target.company or company_identifier(target.url)
        if not ident:
            return SiteOutcome(site=target.url, status=SiteStatus.FAILED, detail="missing company")
        wanted = self.countries
        codes = wanted or ("",)
        jobs: list[JobPosting] = []
        seen: set[str] = set()
        total_found = 0
        for code in codes:
            offset = 0
            total: int | None = None
            while len(jobs) < limit:
                url = postings_url(ident, query, offset, code)
                try:
                    status, body, _final = fetch_public(url)
                except OSError as exc:
                    return SiteOutcome(site=target.url, status=SiteStatus.FAILED, detail=str(exc))
                if status == 404:
                    return SiteOutcome(
                        site=target.url,
                        status=SiteStatus.FAILED,
                        detail=f"HTTP 404 {ident}",
                    )
                if status != 200:
                    return SiteOutcome(
                        site=target.url,
                        status=SiteStatus.FAILED,
                        detail=f"HTTP {status} {ident}",
                    )
                try:
                    payload = json.loads(body)
                except json.JSONDecodeError:
                    return SiteOutcome(
                        site=target.url,
                        status=SiteStatus.CHANGED,
                        detail=f"{ident}: la respuesta no es JSON",
                    )
                if not isinstance(payload, dict):
                    return SiteOutcome(
                        site=target.url,
                        status=SiteStatus.CHANGED,
                        detail=f"{ident}: faltan content o totalFound",
                    )
                parsed = parse_postings(payload, ident)
                if parsed is None:
                    return SiteOutcome(
                        site=target.url,
                        status=SiteStatus.CHANGED,
                        detail=f"{ident}: faltan content o totalFound",
                    )
                page, total = parsed
                total_found = max(total_found, total)
                if not page and offset == 0:
                    break
                for job in page:
                    if not _in_country(job, wanted):
                        continue
                    if filters is not None and not filters.keeps(job):
                        continue
                    key = job.source_job_id or ""
                    if key in seen:
                        continue
                    seen.add(key)
                    jobs.append(job)
                    if len(jobs) >= limit:
                        break
                offset += PAGE_SIZE
                if offset >= total or not page:
                    break
        if not jobs:
            return SiteOutcome(
                site=target.url,
                status=SiteStatus.EMPTY,
                jobs=[],
                feed_size=total_found,
            )
        return SiteOutcome(
            site=target.url,
            status=SiteStatus.OK,
            jobs=jobs[:limit],
            feed_size=total_found,
            kept_ids=tuple(job.source_job_id or "" for job in jobs),
        )


def _board_from_evidence(registry: CompanyRegistry, url: str) -> str:
    """A custom career host names no board; the embed marker that detected it does."""
    row = registry.find_site(url)
    if row is None:
        return ""
    for observation in row[1].observations:
        ident = board_in_text(observation.evidence)
        if ident:
            return ident
    return ""


def _in_country(job: JobPosting, wanted: tuple[str, ...]) -> bool:
    if not wanted:
        return True
    found = {normalize_country(part) for part in (job.location or "").split(",")}
    return any(normalize_country(code) in found for code in wanted)
