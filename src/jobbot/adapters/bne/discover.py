"""`jobs discover --source bne` reads the public list and does not retry it empty."""

from __future__ import annotations

import json
import time
import urllib.request
from urllib.parse import urlsplit

from jobbot.adapters.bne.parse import parse_page, search_url
from jobbot.companies.registry import CompanyRegistry
from jobbot.jobs.discover import JobFilters, SiteOutcome, SiteStatus, SiteTarget
from jobbot.models.job import JobPosting

LISTING = "https://www.bne.cl"


def pause() -> None:
    """At most one request a second. Tests replace this."""
    time.sleep(1)


def fetch_public(url: str) -> tuple[int, str, str]:
    """GET one public JSON page. Tests replace this."""
    pause()
    request = urllib.request.Request(url, headers={"User-Agent": "jobbot/0.1"})
    with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
        status = int(getattr(response, "status", 200))
        body = response.read().decode("utf-8", errors="replace")
        final = str(response.geturl())
    return status, body, final


class BneDiscover:
    """Read `buscarListas`. Zero hits stay zero."""

    name = "bne"
    default_details = False

    def site_target(self, raw: str) -> SiteTarget:
        text = raw.strip()
        host = (urlsplit(text if "://" in text else f"https://{text}").hostname or "").lower()
        if host not in {"bne.cl", "www.bne.cl"}:
            raise ValueError(f"{raw} is not bne.cl")
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
                detail="bne needs a query",
            )
        filters = filters or JobFilters()
        jobs: list[JobPosting] = []
        seen: set[str] = set()
        page_no = 1
        while len(jobs) < limit:
            status, body, _final = fetch_public(search_url(text, page_no))
            if status != 200:
                return SiteOutcome(
                    site=target.url,
                    status=SiteStatus.FAILED,
                    detail=f"HTTP {status}",
                )
            try:
                payload = json.loads(body)
            except json.JSONDecodeError:
                return SiteOutcome(
                    site=target.url,
                    status=SiteStatus.CHANGED,
                    detail="la respuesta no es JSON",
                )
            parsed = parse_page(payload)
            if parsed.changed:
                return SiteOutcome(site=target.url, status=SiteStatus.CHANGED, detail=parsed.detail)
            if parsed.echoed != text:
                return SiteOutcome(
                    site=target.url,
                    status=SiteStatus.CHANGED,
                    detail="textoLibre no coincide",
                )
            if parsed.total == 0:
                return SiteOutcome(
                    site=target.url,
                    status=SiteStatus.EMPTY,
                    detail=f'0 resultados para "{text}"',
                )
            if parsed.active == parsed.total:
                return SiteOutcome(
                    site=target.url,
                    status=SiteStatus.EMPTY,
                    detail="filtro ignorado",
                )
            for job in parsed.jobs:
                if job.source_job_id in seen or not filters.keeps(job):
                    continue
                seen.add(job.source_job_id or "")
                jobs.append(job)
                if len(jobs) >= limit:
                    break
            if page_no >= parsed.pages or not parsed.jobs:
                break
            page_no += 1
        return SiteOutcome(site=target.url, status=SiteStatus.OK, jobs=jobs[:limit])
