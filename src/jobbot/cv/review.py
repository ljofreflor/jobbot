"""A reviewer only keeps or rejects a change. It does not propose a new sentence."""

from __future__ import annotations

import re
from collections import Counter

_NUMBER_GAP = re.compile(r"(?<=\d)[\s.,](?=\d)")
_DIGITS = re.compile(r"\d+")
_WORDS = re.compile(r"[^\W\d_]+", re.UNICODE)
_INTENSIFIERS = frozenset(
    {
        "muy",
        "realmente",
        "bastante",
        "altamente",
        "sumamente",
        "very",
        "really",
        "highly",
        "extremely",
    }
)


def review_change(current: str, proposed: str) -> str:
    """``keep``, ``reject: number`` or ``reject: longer``. A blank side is refused."""
    base = current.strip()
    edited = proposed.strip()
    if not base or not edited:
        raise ValueError("missing text")
    if not _keeps_numbers(base, edited):
        return "reject: number"
    extra = _words(edited) - _words(base)
    if len(edited) > len(base) and extra and extra <= _INTENSIFIERS:
        return "reject: longer"
    return "keep"


def _keeps_numbers(current: str, proposed: str) -> bool:
    have = Counter(_numbers(current))
    got = Counter(_numbers(proposed))
    return all(got[number] >= count for number, count in have.items())


def _numbers(text: str) -> list[str]:
    return _DIGITS.findall(_NUMBER_GAP.sub("", text))


def _words(text: str) -> set[str]:
    return {word.casefold() for word in _WORDS.findall(text)}
