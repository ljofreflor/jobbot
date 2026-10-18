"""`jobs discover --source greenhouse` reads the public Job Board API."""

from __future__ import annotations

import json
import time
import urllib.request

from jobbot.adapters.greenhouse.parse import board_token, job_from_item, parse_board
from jobbot.companies.registry import CompanyRegistry
from jobbot.jobs.discover import (
    JobFilters,
    SiteOutcome,
    SiteStatus,
    SiteTarget,
    registry_sites_for,
)
from jobbot.jobs.normalization import fold_text
from jobbot.models.job import JobPosting


def pause() -> None:
    """At most one request a second. Tests replace this."""
    time.sleep(1)


def fetch_public(url: str) -> tuple[int, str, str]:
    """GET one public API page. Tests replace this. ``/embed/`` is refused."""
    if "/embed/" in url.casefold():
        msg = f"robots.txt disallows {url}"
        raise ValueError(msg)
    pause()
    request = urllib.request.Request(url, headers={"User-Agent": "jobbot/0.1"})
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        status = int(getattr(response, "status", 200))
        body = response.read().decode("utf-8", errors="replace")
        final = str(response.geturl())
    return status, body, final


def jobs_url(token: str, *, content: bool) -> str:
    """Board list. ``content=false`` when this board already has stored jobs."""
    flag = "true" if content else "false"
    return f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs?content={flag}"


def detail_url(token: str, posting_id: str) -> str:
    """One job, used only when it is not already stored."""
    return f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs/{posting_id}"


class GreenhouseDiscover:
    """Read a public board. A 404 is this board's failure; the caller tries the next."""

    name = "greenhouse"
    default_details = False
    known_ids: set[str] = set()

    def site_target(self, raw: str) -> SiteTarget:
        token = board_token(raw)
        return SiteTarget(url=f"https://job-boards.greenhouse.io/{token}", company=token)

    def registry_targets(self, registry: CompanyRegistry) -> list[SiteTarget]:
        found: list[SiteTarget] = []
        for site in registry_sites_for(registry, "greenhouse"):
            try:
                token = board_token(site.url)
            except ValueError:
                continue
            found.append(
                SiteTarget(url=f"https://job-boards.greenhouse.io/{token}", company=token)
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
        token = target.company or board_token(target.url)
        with_content = not self._known_on(token)
        url = jobs_url(token, content=with_content)
        try:
            status, body, _final = fetch_public(url)
        except OSError as exc:
            return SiteOutcome(site=target.url, status=SiteStatus.FAILED, detail=str(exc))
        if status == 404:
            return SiteOutcome(
                site=target.url,
                status=SiteStatus.FAILED,
                detail=f"HTTP 404 {token}; revisar",
            )
        if status != 200:
            return SiteOutcome(
                site=target.url,
                status=SiteStatus.FAILED,
                detail=f"HTTP {status} {token}",
            )
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return SiteOutcome(
                site=target.url,
                status=SiteStatus.CHANGED,
                detail=f"{token}: la respuesta no es JSON",
            )
        if not isinstance(payload, dict):
            return SiteOutcome(
                site=target.url,
                status=SiteStatus.CHANGED,
                detail=f"{token}: falta jobs",
            )
        listed = parse_board(payload, token)
        if listed is None:
            return SiteOutcome(
                site=target.url,
                status=SiteStatus.CHANGED,
                detail=f"{token}: falta jobs",
            )
        jobs: list[JobPosting] = []
        for job in listed:
            posting_id = (job.source_job_id or "").split(":", 1)[-1]
            if not with_content and job.source_job_id not in self.known_ids:
                detailed = self._detail(token, posting_id)
                if detailed is not None:
                    job = detailed
            if not _matches(query, job):
                continue
            if filters is not None and not filters.keeps(job):
                continue
            jobs.append(job)
            if len(jobs) >= limit:
                break
        if not jobs:
            return SiteOutcome(
                site=target.url,
                status=SiteStatus.EMPTY,
                jobs=[],
                feed_size=len(listed),
            )
        return SiteOutcome(
            site=target.url,
            status=SiteStatus.OK,
            jobs=jobs,
            feed_size=len(listed),
            kept_ids=tuple(job.source_job_id or "" for job in jobs),
        )

    def _known_on(self, token: str) -> bool:
        prefix = f"{token}:"
        return any(item.startswith(prefix) for item in self.known_ids)

    def _detail(self, token: str, posting_id: str) -> JobPosting | None:
        status, body, _final = fetch_public(detail_url(token, posting_id))
        if status != 200:
            return None
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        return job_from_item(payload, token)


def _matches(query: str, job: JobPosting) -> bool:
    needle = fold_text(query)
    if not needle:
        return True
    blob = fold_text(f"{job.title} {job.company} {job.location or ''}")
    return needle in blob
