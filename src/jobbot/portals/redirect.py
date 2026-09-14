"""Follow HTTP redirects to resolve short links (lnkd.in, etc.) — no stealth."""

from __future__ import annotations

import logging
import urllib.error
import urllib.request
from urllib.parse import urlparse

logger = logging.getLogger("jobbot.portals.redirect")

_MAX_REDIRECTS = 8
_USER_AGENT = "jobbot/0.1 (local; redirect resolve)"


def follow_redirect_url(url: str, *, timeout: float = 15.0) -> str:
    """Return final URL after redirects; original URL on failure."""
    raw = url.strip()
    if not raw:
        return url
    if not raw.startswith(("http://", "https://")):
        raw = f"https://{raw}"
    current = raw
    for _ in range(_MAX_REDIRECTS):
        req = urllib.request.Request(
            current,
            method="HEAD",
            headers={"User-Agent": _USER_AGENT},
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
                final = resp.geturl() or current
        except urllib.error.HTTPError as exc:
            if exc.code in {301, 302, 303, 307, 308} and exc.headers.get("Location"):
                loc = exc.headers["Location"]
                if loc.startswith("/"):
                    parsed = urlparse(current)
                    loc = f"{parsed.scheme}://{parsed.netloc}{loc}"
                current = loc
                continue
            logger.debug("HEAD failed for %s: %s", current, exc)
            return current
        except OSError as exc:
            logger.debug("Redirect resolve failed for %s: %s", current, exc)
            return current
        if final == current:
            return final
        current = final
    return current


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
