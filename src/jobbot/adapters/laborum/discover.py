"""`jobs discover --source laborum` refuses without fetching the sitemap."""

from __future__ import annotations

from urllib.parse import urlparse

from jobbot.companies.registry import CompanyRegistry
from jobbot.jobs.discover import JobFilters, SiteOutcome, SiteStatus, SiteTarget

HOME = "https://www.laborum.cl/"
TERMS_REASON = (
    "discovery: blocked (terms). Laborum: la decisión de términos no está tomada "
    "(revisado 2026-10-08). Usa jobs add --file."
)


class LaborumDiscover:
    """Terms are not decided. This command does not fetch."""

    name = "laborum"
    default_details = False

    def site_target(self, raw: str) -> SiteTarget:
        text = raw.strip()
        if not text or " " in raw:
            msg = f"{raw} is not a site"
            raise ValueError(msg)
        if "://" not in text:
            text = f"https://{text}"
        if urlparse(text).hostname is None:
            msg = f"{raw} is not a site"
            raise ValueError(msg)
        return SiteTarget(url=text)

    def registry_targets(self, registry: CompanyRegistry) -> list[SiteTarget]:
        del registry
        return [SiteTarget(url=HOME)]

    def discover_site(
        self,
        target: SiteTarget,
        *,
        query: str,
        limit: int,
        details: bool,
        filters: JobFilters | None = None,
    ) -> SiteOutcome:
        del query, limit, details, filters
        return SiteOutcome(site=target.url, status=SiteStatus.ROBOTS, detail=TERMS_REASON)
