"""`jobs discover --source buk` reads robots.txt and then stops."""

from __future__ import annotations

from urllib.parse import urlparse

from jobbot.companies.registry import CompanyRegistry
from jobbot.jobs.discover import (
    JobFilters,
    SiteOutcome,
    SiteStatus,
    SiteTarget,
    registry_sites_for,
)
from jobbot.portals.detect import BUK_ROBOTS_REASON, AtsKind, detect_ats


def fetch_robots(url: str) -> str:
    """GET one robots.txt. Tests replace this; the career page is never requested here."""
    import urllib.request

    request = urllib.request.Request(url, headers={"User-Agent": "jobbot/0.1"})
    with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
        body = response.read()
    return str(body.decode("utf-8", errors="replace"))


def disallows_all(text: str) -> bool:
    """True when `User-agent: *` is followed by `Disallow: /`."""
    agent = ""
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        if key.casefold() == "user-agent":
            agent = value
        elif key.casefold() == "disallow" and agent == "*" and value == "/":
            return True
    return False


class BukDiscover:
    """Recognise a Buk host and refuse to crawl it."""

    name = "buk"
    default_details = False

    def __init__(self) -> None:
        self._robots: dict[str, str] = {}

    def site_target(self, raw: str) -> SiteTarget:
        if detect_ats(raw) is not AtsKind.BUK:
            msg = f"{raw} is not a Buk host (*.buk.cl)"
            raise ValueError(msg)
        return SiteTarget(url=raw)

    def registry_targets(self, registry: CompanyRegistry) -> list[SiteTarget]:
        return registry_sites_for(registry, AtsKind.BUK.value)

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
        host = urlparse(target.url).hostname or ""
        robots_url = f"https://{host}/robots.txt"
        if robots_url not in self._robots:
            self._robots[robots_url] = fetch_robots(robots_url)
        if disallows_all(self._robots[robots_url]):
            return SiteOutcome(
                site=target.url,
                status=SiteStatus.ROBOTS,
                detail=BUK_ROBOTS_REASON,
            )
        return SiteOutcome(
            site=target.url,
            status=SiteStatus.FAILED,
            detail="la fuente sigue deshabilitada hasta revisar términos",
        )
