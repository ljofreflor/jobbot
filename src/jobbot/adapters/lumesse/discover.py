"""`jobs discover --source lumesse` refuses without calling the front-office API."""

from __future__ import annotations

from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

from jobbot.companies.oneshot import USER_AGENT
from jobbot.companies.registry import CompanyRegistry
from jobbot.jobs.discover import JobFilters, SiteOutcome, SiteStatus, SiteTarget, registry_sites_for

_REVIEWED = "2026-10-08"
# The ban lives on TalentLink's front-office host, not on the career site that embeds it.
_ROBOTS_HOST = "recruitmentplatform.com"


def forbids_fo_rest(robots_text: str, url: str) -> bool:
    """True when jobbot's agent may not fetch `url` under this robots.txt."""
    parser = RobotFileParser()
    parser.parse(robots_text.splitlines())
    return not parser.can_fetch(USER_AGENT, url)


def refusal(host: str) -> str:
    """The one sentence `jobs discover --source lumesse` prints."""
    return (
        f"Lumesse TalentLink en {host}: robots.txt de {_ROBOTS_HOST} prohíbe /fo/rest "
        f"para bots que no son de búsqueda (revisado {_REVIEWED}). "
        "Usa jobs add --file. Muchos avisos también aparecen en ReliefWeb (#180)."
    )


class LumesseDiscover:
    """Refuse every site. The platform's robots.txt forbids `/fo/rest` for jobbot."""

    name = "lumesse"
    default_details = False

    def site_target(self, raw: str) -> SiteTarget:
        text = raw.strip()
        if "://" not in text:
            text = f"https://{text}"
        host = urlparse(text).hostname
        if not host or " " in raw:
            msg = f"{raw} is not a site URL"
            raise ValueError(msg)
        return SiteTarget(url=text)

    def registry_targets(self, registry: CompanyRegistry) -> list[SiteTarget]:
        return registry_sites_for(registry, "lumesse")

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
        host = urlparse(target.url).hostname or target.url
        return SiteOutcome(site=target.url, status=SiteStatus.ROBOTS, detail=refusal(host))
