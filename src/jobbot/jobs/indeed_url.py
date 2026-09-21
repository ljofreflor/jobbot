"""Indeed job URL normalization and validation.

Indeed job identity is the `jk` parameter (hex string). Tracking params must be
stripped to store a canonical URL.
"""

from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse, urlunparse


class IndeedUrlError(ValueError):
    """Invalid Indeed job URL (missing jk or wrong host)."""


def canonical_indeed_job_url(url: str) -> str:
    """Canonicalize an Indeed job URL: keep only jk param, preserve country host.
    
    Args:
        url: Indeed viewjob URL with jk parameter
        
    Returns:
        Canonical URL with only jk parameter
        
    Raises:
        IndeedUrlError: If URL is not a valid Indeed viewjob URL or missing jk
        
    Examples:
        >>> canonical_indeed_job_url(
        ...     "https://cl.indeed.com/viewjob?jk=abc123&tk=tracking&from=email"
        ... )
        'https://cl.indeed.com/viewjob?jk=abc123'
    """
    parsed = urlparse(url)
    
    if not parsed.netloc:
        msg = f"Invalid URL: {url}"
        raise IndeedUrlError(msg)
    
    if "indeed.com" not in parsed.netloc:
        msg = f"Not an Indeed URL: {url}"
        raise IndeedUrlError(msg)
    
    if parsed.path != "/viewjob":
        msg = f"Not a viewjob URL: {url} (path must be /viewjob)"
        raise IndeedUrlError(msg)
    
    query_params = parse_qs(parsed.query)
    jk_list = query_params.get("jk", [])
    
    if not jk_list or not jk_list[0]:
        msg = f"Missing jk parameter in Indeed URL: {url}"
        raise IndeedUrlError(msg)
    
    jk = jk_list[0]
    
    if not re.fullmatch(r"[a-f0-9]+", jk):
        msg = f"Invalid jk format (expected hex): {jk}"
        raise IndeedUrlError(msg)
    
    canonical = urlunparse(
        (parsed.scheme or "https", parsed.netloc, parsed.path, "", f"jk={jk}", "")
    )
    return canonical


def extract_jk(url: str) -> str:
    """Extract the jk (job key) from an Indeed URL.
    
    Args:
        url: Indeed viewjob URL
        
    Returns:
        The jk parameter value
        
    Raises:
        IndeedUrlError: If jk cannot be extracted
    """
    parsed = urlparse(url)
    query_params = parse_qs(parsed.query)
    jk_list = query_params.get("jk", [])
    
    if not jk_list or not jk_list[0]:
        msg = f"Missing jk parameter in Indeed URL: {url}"
        raise IndeedUrlError(msg)
    
    return jk_list[0]


def is_indeed_viewjob_url(url: str) -> bool:
    """Check if a URL is an Indeed viewjob URL (may have extra params).
    
    Args:
        url: URL to check
        
    Returns:
        True if it's an Indeed viewjob URL
    """
    try:
        parsed = urlparse(url)
        return (
            "indeed.com" in parsed.netloc
            and parsed.path == "/viewjob"
            and "jk" in parse_qs(parsed.query)
        )
    except Exception:
        return False
