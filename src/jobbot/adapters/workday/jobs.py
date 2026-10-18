"""Workday as a job source: search career sites through CXS and map postings."""

from __future__ import annotations

from jobbot.adapters.workday.cxs import (
    CxsClient,
    WorkdayError,
    WorkdayPostingClosed,
    WorkdayRef,
    WorkdayRefused,
    WorkdayRobotsDisallowed,
    WorkdayShapeChanged,
    WorkdaySite,
    job_from_detail,
    job_from_search_item,
    parse_site_url,
    parse_workday_url,
)
from jobbot.companies.registry import CompanyRegistry
from jobbot.jobs import closing
from jobbot.jobs.discover import (
    JobFilters,
    SiteOutcome,
    SiteStatus,
    SiteTarget,
    registry_sites_for,
)
from jobbot.jobs.sources import JobSearchQuery
from jobbot.models.job import JobPosting
from jobbot.portals.detect import AtsKind


class WorkdayDiscover:
    """`jobs discover --source workday`: one career site per target."""

    name = "workday"
    default_details = True

    def __init__(self, client: CxsClient | None = None) -> None:
        self.client = client or CxsClient()

    def site_target(self, raw: str) -> SiteTarget:
        site = parse_site_url(raw)
        if site is None:
            msg = (
                f"Not a Workday career site: {raw!r}. Expected "
                "https://<tenant>.wdN.myworkdayjobs.com/[<locale>/]<site>"
            )
            raise ValueError(msg)
        return SiteTarget(url=site.url)

    def registry_targets(self, registry: CompanyRegistry) -> list[SiteTarget]:
        out: list[SiteTarget] = []
        seen: set[str] = set()
        for target in registry_sites_for(registry, AtsKind.WORKDAY.value):
            site = parse_site_url(target.url)
            if site is not None and site.url not in seen:
                seen.add(site.url)
                out.append(SiteTarget(url=site.url, company=target.company))
        return out

    def discover_site(
        self,
        target: SiteTarget,
        *,
        query: str,
        limit: int,
        details: bool,
        filters: JobFilters | None = None,
    ) -> SiteOutcome:
        site = parse_site_url(target.url)
        if site is None:
            return SiteOutcome(target.url, SiteStatus.FAILED, detail="not a Workday site")
        try:
            result = self.client.search(site, query, limit=limit)
        except WorkdayRobotsDisallowed as exc:
            return SiteOutcome(site.label, SiteStatus.ROBOTS, detail=str(exc))
        except WorkdayShapeChanged as exc:
            return SiteOutcome(site.label, SiteStatus.CHANGED, detail=str(exc))
        except WorkdayError as exc:
            return SiteOutcome(site.label, SiteStatus.FAILED, detail=str(exc))
        today = closing.utc_now().date()
        jobs: list[JobPosting] = []
        notes: list[str] = []
        for item in result.postings:
            row = job_from_search_item(site, item, company=target.company, today=today)
            if details:
                row = self._with_detail(site, item, row, notes)
            if filters is None or filters.keeps(row):
                jobs.append(row)
        status = SiteStatus.OK if jobs else SiteStatus.EMPTY
        detail = f"{len(jobs)} de {result.total}"
        if filters is not None and filters.active:
            detail += f"; {len(result.postings) - len(jobs)} fuera de --location/--level"
        if notes:
            detail += "; " + "; ".join(notes)
        return SiteOutcome(site.label, status, jobs=jobs, detail=detail, total=result.total)

    def _with_detail(
        self,
        site: WorkdaySite,
        item: dict[str, object],
        row: JobPosting,
        notes: list[str],
    ) -> JobPosting:
        ref = WorkdayRef(site=site, external_path=str(item.get("externalPath") or ""))
        try:
            full = job_from_detail(ref, self.client.job(ref), company=row.company)
        except WorkdayPostingClosed:
            row.ats_signals["can_apply"] = False
            return row
        except WorkdayError as exc:
            notes.append(f"detalle {ref.req_id or ref.external_path}: {exc}")
            return row
        if full.posted_at is None:
            full.posted_at = row.posted_at
        full.note = full.note or row.note
        if row.location and not full.location:
            full.location = row.location
        return full


class WorkdayJobSource:
    """`JobSourceAdapter` view: search the given sites, or read one posting by URL."""

    def __init__(
        self,
        sites: list[str] | None = None,
        *,
        client: CxsClient | None = None,
    ) -> None:
        self.sites = sites or []
        self.discover = WorkdayDiscover(client)

    def search_jobs(self, query: JobSearchQuery) -> list[JobPosting]:
        jobs: list[JobPosting] = []
        for raw in self.sites:
            outcome = self.discover.discover_site(
                self.discover.site_target(raw), query=query.query, limit=query.limit, details=True
            )
            if outcome.status is SiteStatus.FAILED:
                raise WorkdayRefused(outcome.detail)
            jobs.extend(outcome.jobs)
        return jobs

    def get_job(self, job_id: str) -> JobPosting:
        ref = parse_workday_url(job_id)
        if ref is None:
            msg = f"WorkdayJobSource.get_job needs a Workday posting URL, got {job_id!r}"
            raise ValueError(msg)
        return job_from_detail(ref, self.discover.client.job(ref))
