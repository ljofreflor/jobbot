"""`jobs discover --source impactpool` refuses without reading the board."""

from __future__ import annotations

from urllib.parse import urlparse

from jobbot.companies.registry import CompanyRegistry
from jobbot.jobs.discover import JobFilters, SiteOutcome, SiteStatus, SiteTarget
from jobbot.portals.detect import IMPACTPOOL_TERMS_REASON

SEARCH = "https://www.impactpool.org/search"


class ImpactpoolDiscover:
    """The terms forbid copying platform data. This command does not fetch."""

    name = "impactpool"
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
        return [SiteTarget(url=SEARCH)]

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
        return SiteOutcome(
            site=target.url,
            status=SiteStatus.ROBOTS,
            detail=IMPACTPOOL_TERMS_REASON,
        )
