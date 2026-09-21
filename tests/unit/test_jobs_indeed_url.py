"""Indeed URL normalization and validation tests."""

import pytest

from jobbot.jobs.indeed_url import (
    IndeedUrlError,
    canonical_indeed_job_url,
    extract_jk,
    is_indeed_viewjob_url,
)


def test_canonical_indeed_job_url_strips_tracking_params() -> None:
    """Tracking params are stripped; only jk remains."""
    url = "https://cl.indeed.com/viewjob?jk=8a5fab1a7c476a97&tk=tracking&from=email&xpse=123"
    canonical = canonical_indeed_job_url(url)
    
    assert canonical == "https://cl.indeed.com/viewjob?jk=8a5fab1a7c476a97"
    assert "tk=" not in canonical
    assert "from=" not in canonical
    assert "xpse=" not in canonical


def test_canonical_indeed_job_url_preserves_country_host() -> None:
    """Country subdomain is preserved."""
    assert canonical_indeed_job_url(
        "https://cl.indeed.com/viewjob?jk=abc123"
    ) == "https://cl.indeed.com/viewjob?jk=abc123"
    
    assert canonical_indeed_job_url(
        "https://www.indeed.com/viewjob?jk=abc123"
    ) == "https://www.indeed.com/viewjob?jk=abc123"
    
    assert canonical_indeed_job_url(
        "https://mx.indeed.com/viewjob?jk=abc123"
    ) == "https://mx.indeed.com/viewjob?jk=abc123"


def test_canonical_indeed_job_url_requires_jk() -> None:
    """URL without jk parameter is rejected."""
    with pytest.raises(IndeedUrlError, match="Missing jk parameter"):
        canonical_indeed_job_url("https://cl.indeed.com/viewjob?other=param")


def test_canonical_indeed_job_url_requires_indeed_host() -> None:
    """Non-Indeed URLs are rejected."""
    with pytest.raises(IndeedUrlError, match="Not an Indeed URL"):
        canonical_indeed_job_url("https://example.com/viewjob?jk=abc123")


def test_canonical_indeed_job_url_requires_viewjob_path() -> None:
    """URL must be /viewjob path."""
    with pytest.raises(IndeedUrlError, match="path must be /viewjob"):
        canonical_indeed_job_url("https://cl.indeed.com/jobs?jk=abc123")


def test_canonical_indeed_job_url_validates_jk_format() -> None:
    """jk must be hexadecimal."""
    with pytest.raises(IndeedUrlError, match="Invalid jk format"):
        canonical_indeed_job_url("https://cl.indeed.com/viewjob?jk=not-hex-123")


def test_extract_jk() -> None:
    """Extract jk from URL."""
    assert extract_jk("https://cl.indeed.com/viewjob?jk=8a5fab1a7c476a97") == "8a5fab1a7c476a97"
    assert extract_jk("https://cl.indeed.com/viewjob?jk=abc123&other=param") == "abc123"


def test_extract_jk_fails_without_jk() -> None:
    """extract_jk raises when jk is missing."""
    with pytest.raises(IndeedUrlError, match="Missing jk parameter"):
        extract_jk("https://cl.indeed.com/viewjob")


def test_is_indeed_viewjob_url() -> None:
    """Detect valid Indeed viewjob URLs."""
    assert is_indeed_viewjob_url("https://cl.indeed.com/viewjob?jk=abc123")
    assert is_indeed_viewjob_url("https://cl.indeed.com/viewjob?jk=abc&other=param")
    assert not is_indeed_viewjob_url("https://example.com/viewjob?jk=abc")
    assert not is_indeed_viewjob_url("https://cl.indeed.com/jobs?jk=abc")
    assert not is_indeed_viewjob_url("https://cl.indeed.com/viewjob")
    assert not is_indeed_viewjob_url("invalid-url")


def test_canonical_url_is_idempotent() -> None:
    """Canonicalizing a canonical URL returns the same URL."""
    canonical = "https://cl.indeed.com/viewjob?jk=8a5fab1a7c476a97"
    assert canonical_indeed_job_url(canonical) == canonical
