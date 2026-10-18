"""`jobs discover --source cornerstone` refuses without requesting the guest token."""

from __future__ import annotations

from urllib.parse import urlparse

from jobbot.companies.registry import CompanyRegistry
from jobbot.jobs.discover import JobFilters, SiteOutcome, SiteStatus, SiteTarget, registry_sites_for
from jobbot.portals.detect import CORNERSTONE_TOKEN_REASON

_REVIEWED = "2026-10-08"


def refusal(site: str) -> str:
    """The one sentence `jobs discover --source cornerstone` prints."""
    return (
        f"Cornerstone: {CORNERSTONE_TOKEN_REASON} "
        f"Sitio {site} (revisado {_REVIEWED})."
    )


class CornerstoneDiscover:
    """Refuse every site. The search API needs a guest token this command does not take."""

    name = "cornerstone"
    default_details = False

    def site_target(self, raw: str) -> SiteTarget:
        text = raw.strip()
        if not text or " " in raw:
            msg = f"{raw} is not a site"
            raise ValueError(msg)
        if "://" not in text and "." not in text:
            text = f"https://{text}.csod.com"
        elif "://" not in text:
            text = f"https://{text}"
        if urlparse(text).hostname is None:
            msg = f"{raw} is not a site"
            raise ValueError(msg)
        return SiteTarget(url=text)

    def registry_targets(self, registry: CompanyRegistry) -> list[SiteTarget]:
        return registry_sites_for(registry, "cornerstone")

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
        return SiteOutcome(site=target.url, status=SiteStatus.TOKEN, detail=refusal(target.url))
