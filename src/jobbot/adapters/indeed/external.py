"""An Indeed posting whose apply step leaves Indeed."""

from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from jobbot.models.job import JobPosting
from jobbot.portals.detect import detect_ats

_APPLY_TEXT = re.compile(
    r"apply on (?:the )?(?:company|employer) site"
    r"|aplicar en el sitio"
    r"|postular en el sitio"
    r"|sitio (?:web )?de la empresa"
    r"|company site"
    r"|employer site",
    re.IGNORECASE,
)
_TRACKING = frozenset(
    {
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_content",
        "utm_term",
        "from",
        "indeed_apply",
        "sid",
        "rtk",
        "advn",
    }
)


class IndeedVerificationRequired(Exception):
    """The entry page asked for a challenge. One route only; the person continues."""

    def __init__(self, url: str) -> None:
        host = urlsplit(url).hostname or url
        super().__init__(
            f"Indeed asked for an extra verification on {host}. "
            "It stays with you. No other route was tried."
        )
        self.url = url


def read_apply_entry(url: str) -> str:
    """HTML already in hand for the apply entry. Empty by default: this does not fetch.

    Tests replace it. A live fetch of Indeed is out of scope; a challenge is never bypassed.
    """
    del url
    return ""


def gate_indeed_entry(url: str) -> None:
    """Stop when the single entry page is a challenge. Does not try another URL."""
    from jobbot.adapters.indeed.jobs import _looks_like_challenge_html

    body = read_apply_entry(url)
    if body and _looks_like_challenge_html(body):
        raise IndeedVerificationRequired(url)


def external_apply_url(html: str) -> str | None:
    """Destination of an apply control that leaves Indeed, without Indeed tracking."""
    soup = BeautifulSoup(html, "html.parser")
    for anchor in soup.find_all("a", href=True):
        raw = _unwrap(str(anchor["href"]))
        host = urlsplit(raw).hostname or ""
        if not host or _is_indeed_host(host):
            continue
        blob = " ".join(
            (
                anchor.get_text(" ", strip=True),
                str(anchor.get("data-tn-element") or ""),
                str(anchor.get("aria-label") or ""),
            )
        )
        if "externalapply" in blob.casefold() or _APPLY_TEXT.search(blob):
            return strip_indeed_tracking(raw)
    return None


def remember_external_landing(job: JobPosting, final_url: str) -> JobPosting:
    """Keep the host `applystart` actually opened. An Indeed host leaves the job unchanged."""
    raw = _unwrap(final_url)
    host = urlsplit(raw).hostname or ""
    if not host or _is_indeed_host(host):
        return job
    clean = strip_indeed_tracking(raw)
    return job.model_copy(update={"ats_url": clean, "ats_kind": detect_ats(clean).value})


def strip_indeed_tracking(url: str) -> str:
    parts = urlsplit(url)
    kept = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.casefold() not in _TRACKING and not key.casefold().startswith("utm_")
    ]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(kept), ""))


def _unwrap(url: str) -> str:
    parts = urlsplit(url)
    host = parts.hostname or ""
    if _is_indeed_host(host) and ("rclk" in parts.path or parts.path.startswith("/rc/clk")):
        dest = dict(parse_qsl(parts.query)).get("dest")
        if dest:
            return dest
    return url


def _is_indeed_host(host: str) -> bool:
    folded = host.casefold().removeprefix("www.")
    return folded == "indeed.com" or folded.endswith(".indeed.com")
