"""A portal health check names reachability. It does not search for postings."""

from __future__ import annotations

_REFUSED = frozenset({403, 429})


def portal_health(*, status: int | None, robots_disallow: bool = False) -> str:
    """``omitted``, ``reachable``, ``refused`` or ``unknown``. Never a job list."""
    if robots_disallow:
        return "omitted"
    if status is None or status in _REFUSED or (status is not None and status >= 500):
        return "refused"
    if status == 200:
        return "reachable"
    return "unknown"
