"""A posting is someone else's text. A line that instructs the tool is not a fact."""

from __future__ import annotations

import re

# Structural orders, not the vocabulary of a role. A URL in one of these lines is
# not a page to open. An order has to address the tool: «disregard any instructions
# asking for money» and «you are now responsible for the budget» are the posting
# talking to its reader, and dropping them would lose real duties.
_INSTRUCTION = re.compile(
    r"(?i)(?:"
    r"(?:ignore|disregard)\s+(?:all\s+|any\s+)?(?:prior|previous|above|earlier)\s+instructions"
    r"|you\s+are\s+now\s+(?:a|an|the)\s+(?:\w+\s+){0,2}"
    r"(?:ai|a\.i\.|llm|language\s+model|assistant|chatbot|bot)\b"
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
