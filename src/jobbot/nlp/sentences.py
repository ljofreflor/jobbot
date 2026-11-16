"""Sentence boundaries that keep an abbreviation in the same sentence."""

from __future__ import annotations

import re

# One list. Longer forms first when a shorter one is a prefix (S.p.A. before S.A.).
ABBREVIATIONS: tuple[str, ...] = (
    "S.p.A.",
    "EE.UU.",
    "S.A.",
    "Ltda.",
    "Sra.",
    "Sr.",
    "Dra.",
    "Dr.",
    "Av.",
    "Inc.",
    "Ltd.",
    "etc.",
    "N°",
    "Nº",
)

_DOT = "\u0001"
_SPLIT = re.compile(r"(?<=[.!?;])\s+|\n+")
_STEMS = {item.casefold().rstrip(".") for item in ABBREVIATIONS}


def is_abbreviation(token: str) -> bool:
    """True for `S.A.` and for the same token with the last dot already stripped."""
    cleaned = token.strip(".,;:()[]\"'").casefold().rstrip(".")
    return cleaned in _STEMS


def split_sentences(text: str) -> list[str]:
    """Split on sentence punctuation, not on a dot that belongs to an abbreviation."""
    protected = text or ""
    for abbr in sorted(ABBREVIATIONS, key=len, reverse=True):
        if "." not in abbr:
            continue
        token = abbr.replace(".", _DOT)
        protected = re.sub(re.escape(abbr), token, protected, flags=re.IGNORECASE)
    out: list[str] = []
    for part in _SPLIT.split(protected):
        cleaned = part.strip().replace(_DOT, ".")
        if cleaned:
            out.append(cleaned)
    return out
