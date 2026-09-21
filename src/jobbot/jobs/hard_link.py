"""Fetch and store individual job postings from hard links (URLs).

Hard link: a direct URL to one vacancy (Indeed viewjob, GetOnBoard job page, etc.).
The candidate arrives with the link; JobBot fetches and stores it without search.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from jobbot.jobs.indeed_url import (
    IndeedUrlError,
    canonical_indeed_job_url,
    extract_jk,
)
from jobbot.models.job import JobPosting
from jobbot.portals.detect import AtsKind

# Re-export for convenience
__all__ = ["IndeedUrlError", "HardLinkFetchError", "UnsupportedPortalError", "fetch_from_url"]


class HardLinkFetchError(Exception):
    """Failed to fetch or parse a job from a hard link."""


class UnsupportedPortalError(HardLinkFetchError):
    """Portal is recognized but hard link fetching is not implemented."""


@dataclass(frozen=True)
class HardLinkResult:
    """Result of fetching a job from a hard link."""

    job: JobPosting
    canonical_url: str
    portal: str


def fetch_indeed_job(url: str, *, html: str | None = None) -> HardLinkResult:
    """Fetch an Indeed job from a viewjob URL.
    
    Args:
        url: Indeed viewjob URL with jk parameter
        html: Optional HTML content (for fixtures/offline testing)
        
    Returns:
        HardLinkResult with the fetched job
        
    Raises:
        IndeedUrlError: If URL is invalid
        HardLinkFetchError: If fetch/parse fails
    """
    from jobbot.adapters.indeed.jobs import card_to_job_posting, parse_indeed_job_detail_html

    canonical = canonical_indeed_job_url(url)
    jk = extract_jk(canonical)

    if html is None:
        msg = "Live fetching not implemented yet; use --fixture for now"
        raise HardLinkFetchError(msg)

    try:
        detail = parse_indeed_job_detail_html(html)
    except Exception as exc:
        msg = f"Failed to parse Indeed job HTML: {exc}"
        raise HardLinkFetchError(msg) from exc

    card = {
        "source_job_id": jk,
        "url": canonical,
        "title": detail.get("title"),
        "company": detail.get("company"),
        "location": detail.get("location"),
        "snippet": detail.get("description"),
    }

    job = card_to_job_posting(card, detail_html=html, placeholder_id="PENDING")
    job.url = canonical
    job.source_job_id = jk
    job.discovered_at = datetime.now(UTC)

    return HardLinkResult(job=job, canonical_url=canonical, portal="indeed")


def detect_portal(url: str) -> AtsKind:
    """Detect which portal a URL belongs to.
    
    Args:
        url: Job URL
        
    Returns:
        AtsKind for the detected portal
    """
    from jobbot.portals.detect import detect_ats

    return detect_ats(url)


def fetch_from_url(url: str, *, fixture: Path | None = None) -> HardLinkResult:
    """Fetch a job from a hard link URL.
    
    Args:
        url: Job URL (Indeed, GetOnBoard, etc.)
        fixture: Optional path to HTML fixture for offline testing
        
    Returns:
        HardLinkResult with the fetched job
        
    Raises:
        UnsupportedPortalError: Portal is known but not supported yet
        HardLinkFetchError: Fetch or parse failed
        IndeedUrlError: Invalid Indeed URL
    """
    from jobbot.jobs.indeed_url import is_indeed_viewjob_url

    html = fixture.read_text(encoding="utf-8") if fixture else None

    if is_indeed_viewjob_url(url):
        return fetch_indeed_job(url, html=html)

    portal = detect_portal(url)
    msg = (
        f"Hard link fetching not implemented for {portal.value}; "
        "use 'jobs add --file' as workaround"
    )
    raise UnsupportedPortalError(msg)
