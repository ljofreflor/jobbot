"""A posting is someone else's text. A line that instructs the tool is not a fact."""

from __future__ import annotations

import re

# Structural orders, not the vocabulary of a role. A URL in one of these lines is
# not a page to open.
_INSTRUCTION = re.compile(
    r"(?i)(?:"
    r"ignore\s+(?:all\s+|any\s+)?previous\s+instructions"
    r"|disregard\s+(?:all\s+|any\s+)?(?:prior\s+|previous\s+)?instructions"
    r"|you\s+are\s+now"
    r"|\bfetch\s+https?://"
    r"|\b(?:download|curl|wget)\s+https?://"
    r")"
)


def is_instruction(line: str) -> bool:
    """True when a line tells the tool what to do instead of describing the role."""
    return _INSTRUCTION.search(line or "") is not None


def for_scoring(text: str) -> str:
    """The posting with instruction lines removed. Storage keeps the original."""
    return "\n".join(line for line in (text or "").splitlines() if not is_instruction(line))
