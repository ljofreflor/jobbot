"""Follow HTTP redirects to resolve short links (lnkd.in, etc.) — no stealth."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlparse

import httpx

logger = logging.getLogger("jobbot.portals.redirect")

_MAX_REDIRECTS = 8
_USER_AGENT = "jobbot/0.1 (local; redirect resolve)"


def _client(**kwargs: Any) -> httpx.Client:
    """Seam for tests: httpx handles the redirect chain and relative locations."""
    return httpx.Client(**kwargs)


def follow_redirect_url(url: str, *, timeout: float = 15.0) -> str:
    """Return final URL after redirects; original URL on failure."""
    raw = url.strip()
    if not raw:
        return url
    target = raw if raw.startswith(("http://", "https://")) else f"https://{raw}"
    try:
        with _client(
            follow_redirects=True,
            max_redirects=_MAX_REDIRECTS,
            timeout=timeout,
            headers={"User-Agent": _USER_AGENT},
        ) as client:
            response = client.head(target)
            # Plenty of ATS hosts answer HEAD with 405/501 but redirect fine on GET.
            if response.status_code >= 400:
                response = client.get(target)
            return str(response.url)
    except httpx.HTTPError as exc:
        logger.debug("Redirect resolve failed for %s: %s", target, exc)
        return target


def expand_urls(urls: list[str]) -> list[str]:
    """Resolve redirects; dedupe while preserving order."""
    out: list[str] = []
    seen: set[str] = set()
    for url in urls:
        host = (urlparse(url).hostname or "").lower()
        resolved = follow_redirect_url(url) if _should_resolve(host) else url
        for candidate in (url, resolved):
            if candidate and candidate not in seen:
                seen.add(candidate)
                out.append(candidate)
    return out


def _should_resolve(host: str) -> bool:
    if not host:
        return False
    if host.endswith("lnkd.in") or host == "lnkd.in":
        return True
    return bool("linkedin.com" in host and "redir" in host)
