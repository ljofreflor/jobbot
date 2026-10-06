"""Treat a job posting as untrusted input when scoring or prompting.

The stored JD stays verbatim. Scoring and LLM prompts use a view that drops
injection-shaped lines and does not follow URLs embedded in the body (#201).
"""

from __future__ import annotations

import re

# Lines that look like prompt injection or ask the agent to fetch something.
_INJECTION_LINE = re.compile(
    r"(?i)(?:"
    r"^\s*(?:"
    r"ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions?"
    r"|disregard\s+(?:all\s+)?(?:previous|prior|above)"
    r"|system\s*:\s*"
    r"|you\s+are\s+now\s+"
    r"|ignora\s+(?:todas\s+)?(?:las\s+)?instrucciones?"
    r")\b"
    r"|(?:please\s+)?(?:fetch|download|open|visitar?)\s+https?://"
    r")"
)

# Bare URLs that an agent might fetch from the body — stripped for scoring only.
_URL = re.compile(r"https?://[^\s<>\"']+", re.I)


def scoring_text(text: str) -> str:
    """JD text safe for match / skill extraction: no injection lines, no fetchable URLs.

    Does not mutate the stored posting. Empty input stays empty.
    """
    if not text:
        return text
    kept: list[str] = []
    for line in text.splitlines():
        if _INJECTION_LINE.search(line):
            continue
        kept.append(_URL.sub(" ", line))
    return "\n".join(kept)
