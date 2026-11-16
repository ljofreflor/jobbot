"""A LaTeX log names overfull boxes and how many pages were written."""

from __future__ import annotations

import re

_OVERFULL = re.compile(r"Overfull \\hbox \(([\d.]+)pt too wide\)")
_PAGES = re.compile(r"Output written on \S+ \((\d+) page")


def layout_findings(log: str) -> list[str]:
    """Each overfull hbox, as ``overfull <pt>pt``. Underfull lines are not findings."""
    return [f"overfull {match.group(1)}pt" for match in _OVERFULL.finditer(log)]


def pages_written(log: str) -> int | None:
    """The page count from ``Output written``, or None when the log never finished."""
    found = _PAGES.search(log)
    return int(found.group(1)) if found else None
