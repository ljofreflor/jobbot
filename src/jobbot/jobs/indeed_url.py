"""Indeed job URL canonicalization and validation."""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse


class IndeedUrlError(ValueError):
    """Invalid Indeed job URL."""


def canonical_indeed_job_url(url: str) -> str:
    """Extract canonical Indeed job URL (country host + jk only).
    
    Args:
        url: Indeed job URL (viewjob or with tracking params)
        
    Returns:
        Canonical URL: https://<country>.indeed.com/viewjob?jk=<hex>
        
    Raises:
        IndeedUrlError: URL is not a valid Indeed job URL or missing jk
        
    Examples:
        >>> canonical_indeed_job_url("https://cl.indeed.com/viewjob?jk=abc123&from=email")
        'https://cl.indeed.com/viewjob?jk=abc123'
    """
    if not url:
        raise IndeedUrlError("Empty URL")
    
    parsed = urlparse(url)
    
    # Validate host
    if not parsed.hostname:
        raise IndeedUrlError(f"No hostname in URL: {url}")
    
    host_lower = parsed.hostname.lower()
    if not host_lower.endswith(".indeed.com") and host_lower != "indeed.com":
        raise IndeedUrlError(f"Not an Indeed URL: {url}")
    
    # Extract jk parameter
    query_params = parse_qs(parsed.query)
    jk_values = query_params.get("jk", [])
    
    if not jk_values or not jk_values[0]:
        raise IndeedUrlError(f"Missing 'jk' parameter in URL: {url}")
    
    jk = jk_values[0]
    
    # Validate jk format (hex string)
    if not re.match(r"^[a-f0-9]+$", jk, re.IGNORECASE):
        raise IndeedUrlError(f"Invalid 'jk' format (expected hex): {jk}")
    
    # Reconstruct canonical URL preserving original country host
    scheme = parsed.scheme or "https"
    host = parsed.hostname
    
    return f"{scheme}://{host}/viewjob?jk={jk}"


def extract_indeed_jk(url: str) -> str:
    """Extract the jk (job key) from an Indeed URL.
    
    Args:
        url: Indeed job URL
        
    Returns:
        The jk parameter value
        
    Raises:
        IndeedUrlError: URL is invalid or missing jk
    """
    # Reuse canonicalization to validate and extract
    canonical = canonical_indeed_job_url(url)
    match = re.search(r"jk=([a-f0-9]+)", canonical, re.IGNORECASE)
    if not match:
        raise IndeedUrlError(f"Could not extract jk from URL: {url}")
    return match.group(1)
