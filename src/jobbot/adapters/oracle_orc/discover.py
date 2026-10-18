"""`jobs discover --source oracle_orc` reads the public requisition search."""

from __future__ import annotations

import json
import time
import urllib.request
from urllib.parse import urlencode

from jobbot.adapters.oracle_orc.parse import (
    PAGE_SIZE,
    apply_detail,
    job_from_row,
    parse_list,
    parse_site,
)
from jobbot.companies.registry import CompanyRegistry
from jobbot.jobs.discover import (
    JobFilters,
    SiteOutcome,
    SiteStatus,
    SiteTarget,
    registry_sites_for,
)
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


def search_url(host: str, site: str, query: str, offset: int) -> str:
    """Finder with siteNumber, keyword and offset. Page size is 25."""
    keyword = f',keyword="{query}"' if query.strip() else ""
    finder = f"findReqs;siteNumber={site}{keyword},limit={PAGE_SIZE},offset={offset}"
    params = urlencode(
        {"onlyData": "true", "expand": "requisitionList", "finder": finder}
    )
    return f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitions?{params}"


def detail_url(host: str, site: str, posting_id: str) -> str:
    """One requisition. Not requested again once that id is stored."""
    finder = f'ById;Id="{posting_id}",siteNumber={site}'
    params = urlencode({"expand": "all", "onlyData": "true", "finder": finder})
    return (
        f"https://{host}/hcmRestApi/resources/latest/recruitingCEJobRequisitionDetails?{params}"
    )


class OracleOrcDiscover:
    """Page a public ORC site. A 403 is this site's failure; the caller tries the next.

    The closing date and the long description arrive only on the detail, so a requisition
    that is already stored is left out: its list row alone would overwrite both.
    """

    name = "oracle_orc"
    default_details = False
    known_ids: set[str] = set()

    def site_target(self, raw: str) -> SiteTarget:
        parsed = parse_site(raw)
        if parsed is None:
            msg = f"{raw} needs host/siteNumber"
            raise ValueError(msg)
        host, site = parsed
        url = f"https://{host}/hcmUI/CandidateExperience/en/sites/{site}"
        return SiteTarget(url=url, company=site)

    def registry_targets(self, registry: CompanyRegistry) -> list[SiteTarget]:
        found: list[SiteTarget] = []
        for site in registry_sites_for(registry, "oracle"):
            parsed = parse_site(site.url)
            if parsed is None:
                continue
            host, number = parsed
            url = f"https://{host}/hcmUI/CandidateExperience/en/sites/{number}"
            found.append(SiteTarget(url=url, company=site.company or number))
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
        parsed = parse_site(target.url)
        if parsed is None:
            return SiteOutcome(
                site=target.url,
                status=SiteStatus.FAILED,
                detail="missing siteNumber",
            )
        host, site = parsed
        jobs: list[JobPosting] = []
        seen: set[str] = set()
        offset = 0
        total = 0
        while len(jobs) < limit:
            url = search_url(host, site, query, offset)
            try:
                status, body, _final = fetch_public(url)
            except OSError as exc:
                return SiteOutcome(site=target.url, status=SiteStatus.FAILED, detail=str(exc))
            if status in {401, 403, 404} or status >= 500:
                return SiteOutcome(
                    site=target.url,
                    status=SiteStatus.FAILED,
                    detail=f"HTTP {status} {host}",
                )
            if status != 200:
                return SiteOutcome(
                    site=target.url,
                    status=SiteStatus.FAILED,
                    detail=f"HTTP {status} {host}",
                )
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                return SiteOutcome(
                    site=target.url,
                    status=SiteStatus.CHANGED,
                    detail=f"{host}: la respuesta no es JSON",
                )
            if not isinstance(payload, dict):
                return SiteOutcome(
                    site=target.url,
                    status=SiteStatus.CHANGED,
                    detail=f"{host}: falta requisitionList",
                )
            listed = parse_list(payload)
            if listed is None:
                return SiteOutcome(
                    site=target.url,
                    status=SiteStatus.CHANGED,
                    detail=f"{host}: falta requisitionList",
                )
            rows, total = listed
            if not rows and offset == 0:
                break
            for row in rows:
                label = target.company if target.company and target.company != site else None
                job = job_from_row(row, host=host, site=site, company=label)
                if job is None or job.source_job_id in seen:
                    continue
                if job.source_job_id in self.known_ids:
                    continue
                job = self._with_detail(job, host, site)
                if filters is not None and not filters.keeps(job):
                    continue
                seen.add(job.source_job_id or "")
                jobs.append(job)
                if len(jobs) >= limit:
                    break
            offset += PAGE_SIZE
            if offset >= total or not rows:
                break
        if not jobs:
            return SiteOutcome(site=target.url, status=SiteStatus.EMPTY, jobs=[], feed_size=total)
        return SiteOutcome(
            site=target.url,
            status=SiteStatus.OK,
            jobs=jobs[:limit],
            feed_size=total,
            kept_ids=tuple(job.source_job_id or "" for job in jobs),
        )

    def _with_detail(self, job: JobPosting, host: str, site: str) -> JobPosting:
        """The list row stands when that requisition's detail cannot be read."""
        posting_id = (job.source_job_id or "").split(":")[-1]
        try:
            status, body, _final = fetch_public(detail_url(host, site, posting_id))
        except OSError:
            return job
        if status != 200:
            return job
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return job
        if not isinstance(payload, dict):
            return job
        return apply_detail(job, payload)
