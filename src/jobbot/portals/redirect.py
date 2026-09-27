"""Follow HTTP redirects to resolve short links (lnkd.in, etc.) — no stealth."""

from __future__ import annotations

import logging
import re
import urllib.error
import urllib.request
from urllib.parse import urlparse

logger = logging.getLogger("jobbot.portals.redirect")

_MAX_REDIRECTS = 8
_USER_AGENT = "jobbot/0.1 (local; redirect resolve)"
_MAX_INTERSTITIAL_BYTES = 512_000

# LinkedIn no longer 30x-redirects a lnkd.in link that leaves the site: it answers 200 with
# "This link will take you to a page that's not on LinkedIn" and prints the destination in a
# single anchor. That anchor is LinkedIn stating the target, so reading it is not evasion.
_INTERSTITIAL_DEST_RE = re.compile(
    r"<a\b[^>]*\bdata-tracking-control-name=\"external_url_click\"[^>]*\bhref=\"([^\"]+)\"",
    re.IGNORECASE,
)


def read_interstitial_destination(html: str) -> str | None:
    """External URL declared by LinkedIn's leaving-the-site page, or None."""
    match = _INTERSTITIAL_DEST_RE.search(html or "")
    if match is None:
        return None
    dest = match.group(1).strip()
    return dest if dest.startswith(("http://", "https://")) else None


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
            destination = _interstitial_destination(current, timeout=timeout)
            if destination is None or destination == current:
                return current
            current = destination
            continue
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


def _interstitial_destination(url: str, *, timeout: float) -> str | None:
    """Destination behind a short link that answered 200 with an interstitial page."""
    host = (urlparse(url).hostname or "").lower()
    if not (host == "lnkd.in" or host.endswith(".lnkd.in")):
        return None
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            body = resp.read(_MAX_INTERSTITIAL_BYTES)
    except OSError as exc:
        logger.debug("Interstitial fetch failed for %s: %s", url, exc)
        return None
    return read_interstitial_destination(body.decode("utf-8", errors="replace"))
