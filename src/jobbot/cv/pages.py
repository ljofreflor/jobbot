"""How many pages the PDF took, and what to shorten before deleting a fact."""

from __future__ import annotations

import re
from dataclasses import dataclass

_PAGES = re.compile(r"Output written on \S+ \((\d+) pages?\b")


@dataclass(frozen=True)
class PageTrim:
    """Levers, in order: compact old roles, drop courses, then warn."""

    compact_ids: tuple[str, ...]
    drop_course_ids: tuple[str, ...]
    warning: str | None


def pages_from_xelatex_log(text: str) -> int | None:
    """The last 'Output written on cv.pdf (N pages' line, if XeLaTeX finished."""
    found = _PAGES.findall(text)
    if not found:
        return None
    return int(found[-1])


def plan_page_trim(
    *,
    pages: int | None,
    max_pages: int | None,
    finished: list[tuple[str, str]],
    already_compact: set[str] | None = None,
    course_ids: list[str] | None = None,
) -> PageTrim:
    """When the PDF is over the limit: oldest finished role first, then courses, then a warning.

    ``finished`` is ``(experience id, end_date)``. Current roles are not in that list.
    Nothing is removed from the profile; this only names presentation cuts.
    """
    if max_pages is None or pages is None or pages <= max_pages:
        return PageTrim((), (), None)
    compact_already = already_compact or set()
    ordered = sorted(finished, key=lambda item: item[1])
    compact = tuple(eid for eid, _end in ordered if eid not in compact_already)
    drop = tuple(course_ids or [])
    warning = (
        f"{pages} pages exceeds max_pages {max_pages} "
        "after compacting old roles and dropping courses"
    )
    return PageTrim(compact, drop, warning)
