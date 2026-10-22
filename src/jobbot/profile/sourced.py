"""A fact from a declared source waits for confirmation. It is not written."""

from __future__ import annotations

_SOURCES = frozenset({"github", "portfolio", "scholar"})


def confirm_sourced_fact(text: str, source: str) -> str:
    """The confirmation line. An unknown source or a blank fact is refused."""
    fact = text.strip()
    origin = source.strip().casefold()
    if not fact:
        raise ValueError("missing fact")
    if origin not in _SOURCES:
        raise ValueError("unknown source")
    return f"confirm: {fact} (source: {origin})"
