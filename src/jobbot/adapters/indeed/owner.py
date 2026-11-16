"""The open Indeed resume must name this workspace before anything is typed.

``127.0.0.1`` and ``::1`` on the same port are different browsers. A pass on one
does not authorize the other. The refusal never includes the other person's name.
"""

from __future__ import annotations

import re

from jobbot.browser.cdp import cdp_endpoint
from jobbot.jobs.normalization import fold_text

_NAME_LINE = re.compile(r"[^\W\d_]{2,}(?:\s+[^\W\d_]{2,})+", re.UNICODE)


class IndeedOwnerMismatch(Exception):
    """Writing stopped. ``str(self)`` does not name the other account."""


def cv_name_verdict(page_text: str, owner_name: str) -> str:
    """``match``, ``mismatch``, or ``missing`` when the page shows no name."""
    owner = " ".join(fold_text(owner_name).split())
    if owner and owner in fold_text(page_text):
        return "match"
    if _NAME_LINE.search(page_text or ""):
        return "mismatch"
    return "missing"


def refuse_indeed_write(page_text: str, owner_name: str) -> str | None:
    """None when the open resume names the owner. Otherwise a message with no other identity."""
    verdict = cv_name_verdict(page_text, owner_name)
    if verdict == "match":
        return None
    if verdict == "missing":
        return "Indeed resume has no visible name. Nothing was typed."
    return "Indeed resume name does not match this workspace. Nothing was typed."


def write_allowed(checks: dict[str, str], url: str) -> bool:
    """A match is stored per CDP host, not per port."""
    return checks.get(cdp_endpoint(url)) == "match"
