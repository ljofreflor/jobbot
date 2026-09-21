"""Test jobbot get command for Indeed hard links."""

from __future__ import annotations

from pathlib import Path

import pytest

from jobbot.jobs.from_url import UnsupportedPortalFetchError, ingest_hard_link


def test_get_indeed_job_with_fixture(project_root: Path) -> None:
    """Parse Indeed job from fixture."""
    fixture = project_root / "tests" / "fixtures" / "indeed_job_detail.html"
    url = "https://cl.indeed.com/viewjob?jk=8a5fab1a7c476a97"
    
    job = ingest_hard_link(url, fixture_path=fixture)
    
    assert job.source == "indeed"
    assert job.source_job_id == "8a5fab1a7c476a97"
    assert job.url == url
    assert job.title  # Should have parsed title from fixture


def test_get_strips_tracking_params_from_stored_url(project_root: Path) -> None:
    """Tracking params must not appear in stored URL."""
    fixture = project_root / "tests" / "fixtures" / "indeed_job_detail.html"
    url_with_tracking = "https://cl.indeed.com/viewjob?jk=abc123&from=email&tk=xyz"
    
    job = ingest_hard_link(url_with_tracking, fixture_path=fixture)
    
    assert job.url == "https://cl.indeed.com/viewjob?jk=abc123"
    assert "from=" not in job.url
    assert "tk=" not in job.url


def test_get_rejects_url_without_jk() -> None:
    """URL without jk parameter is a validation error."""
    with pytest.raises(ValueError, match="Missing 'jk'"):
        ingest_hard_link("https://cl.indeed.com/viewjob?foo=bar")


def test_get_rejects_non_indeed_url() -> None:
    """Only Indeed URLs are supported for now."""
    with pytest.raises((ValueError, UnsupportedPortalFetchError)):
        ingest_hard_link("https://linkedin.com/jobs/view/123")


def test_unsupported_portal_raises_clear_error() -> None:
    """Recognized but unsupported portals give clear error."""
    # GetOnBoard is recognized but not yet implemented
    with pytest.raises(UnsupportedPortalFetchError, match="Get on Board"):
        ingest_hard_link("https://www.getonbrd.com/jobs/programming/data-scientist-acme")
