"""Stable public identity for a job URL.

The share code is a fixed-length hash of the canonical URL. It does not grow
when two different URLs collide: lookup then returns both jobs. A mailto address
is personal and has no share code. The path is part of the key, so a new slug
is a different job.
"""

from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlencode, urlsplit

# Fixed on purpose. Lengthening a collision locally would make another machine
# compute a different code for the same URL.
SHARE_CODE_LENGTH = 12

# Names that identify the reader, not the vacancy. Other query keys stay:
# an Indeed posting is `viewjob?jk=`, and dropping the whole query would
# merge every opening on that host into one job.
_TRACKING_NAMES = frozenset(
    {
        "rcm",
        "fbclid",
        "gclid",
        "mc_eid",
        "mc_cid",
        "igshid",
        "_hsenc",
        "_hsmi",
        "si",
        "trk",
        "trackingid",
    }
)


def canonical_job_key(url: str) -> str | None:
    """Host + path + non-tracking query, or None when the URL is not public."""
    raw = (url or "").strip()
    if not raw or raw.lower().startswith("mailto:"):
        return None
    if not re.match(r"^https?://", raw, re.I):
        return None
    parsed = urlsplit(raw)
    host = (parsed.hostname or "").lower().removeprefix("www.")
    if not host:
        return None
    path = re.sub(r"/{2,}", "/", parsed.path or "").rstrip("/")
    kept: list[tuple[str, str]] = []
    for name, value in parse_qsl(parsed.query, keep_blank_values=False):
        folded = name.casefold()
        if folded.startswith("utm_") or folded in _TRACKING_NAMES:
            continue
        kept.append((name, value))
    kept.sort()
    query = urlencode(kept)
    return f"{host}{path}" + (f"?{query}" if query else "")


def share_code_for_key(key: str) -> str:
    """Twelve hex characters. Always this length."""
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return digest[:SHARE_CODE_LENGTH]


def share_code_for_url(url: str) -> str | None:
    key = canonical_job_key(url)
    if key is None:
        return None
    return share_code_for_key(key)


def display_url(url: str) -> str | None:
    """Public URL with tracking parameters removed. None for mailto and non-http."""
    key = canonical_job_key(url)
    if key is None:
        return None
    return f"https://{key}"
