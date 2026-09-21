"""Fetch job postings from hard links (direct URLs)."""

from __future__ import annotations

import logging
from pathlib import Path

from jobbot.adapters.indeed.jobs import IndeedJobSource
from jobbot.jobs.indeed_url import canonical_indeed_job_url, extract_indeed_jk
from jobbot.models.job import JobPosting
from jobbot.portals.detect import AtsKind, detect_ats

logger = logging.getLogger("jobbot.jobs.from_url")


class UnsupportedPortalFetchError(ValueError):
    """Portal is recognized but hard-link fetch is not implemented."""


def ingest_hard_link(
    url: str,
    *,
    fixture_path: Path | None = None,
    cdp_url: str | None = None,
) -> JobPosting:
    """Fetch a job posting from a direct URL.
    
    Args:
        url: Direct job posting URL
        fixture_path: Optional HTML fixture for offline parsing
        cdp_url: Optional CDP endpoint for browser automation
        
    Returns:
        JobPosting with source/source_job_id populated
        
    Raises:
        UnsupportedPortalFetchError: Portal recognized but not supported
        IndeedUrlError: Invalid Indeed URL
        ValueError: Unknown or invalid URL
    """
    ats_kind = detect_ats(url)
    
    if ats_kind == AtsKind.INDEED:
        return _fetch_indeed_job(url, fixture_path=fixture_path, cdp_url=cdp_url)
    
    if ats_kind == AtsKind.GETONBOARD:
        raise UnsupportedPortalFetchError(
            "Get on Board hard links are not yet implemented for jobbot get"
        )
    
    if ats_kind != AtsKind.UNKNOWN:
        raise UnsupportedPortalFetchError(
            f"Hard-link fetch for {ats_kind.value} is not implemented"
        )
    
    raise ValueError(f"Unknown portal or invalid URL: {url}")


def _fetch_indeed_job(
    url: str,
    *,
    fixture_path: Path | None = None,
    cdp_url: str | None = None,
) -> JobPosting:
    """Fetch an Indeed job by URL or fixture."""
    # Canonicalize URL first
    canonical_url = canonical_indeed_job_url(url)
    jk = extract_indeed_jk(canonical_url)
    
    if fixture_path:
        # Parse from fixture
        html = fixture_path.read_text(encoding="utf-8")
        from jobbot.adapters.indeed.jobs import card_to_job_posting
        
        card = {
            "source_job_id": jk,
            "url": canonical_url,
            "title": "",
            "company": "",
            "location": None,
            "snippet": "",
        }
        job = card_to_job_posting(card, detail_html=html, placeholder_id="TMP")
        job.url = canonical_url
        job.source_job_id = jk
        return job
    
    # Fetch live
    source = IndeedJobSource(cdp_url=cdp_url)
    job = source.get_job(jk)
    job.url = canonical_url
    job.source_job_id = jk
    return job
