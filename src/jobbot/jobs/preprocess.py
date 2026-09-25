"""Deterministic cleanup before parsing a pasted / LinkedIn / email JD.

Strips chrome that is not a skill or requirement so both the regex parser and a
chat-first LLM see employment signal, not share metadata.
"""

from __future__ import annotations

import re

_HASHTAG_RE = re.compile(r"(?i)(?:^|\s)#[\wáéíóúñ]+")
_META_LINE_RE = re.compile(
    r"(?i)^(?:"
    r"publicado\b.*|"
    r"hace\s+\d+\s+\w+|"
    r"postulaci[oó]n\s*:|"
    r"enviar\s+cv\s+a\b|"
    r"send\s+(?:your\s+)?cv\s+to\b|"
    r"mailto:|"
    r"[\w.+-]+@[\w.-]+\.\w+"
    r").*$"
)
_EMPHASIS_RE = re.compile(r"[*_`]+")


def preprocess_job_text(text: str) -> str:
    """Return a scrubbed JD: no hashtags, share meta, or bare emails as lines."""
    lines_out: list[str] = []
    for raw in text.splitlines():
        line = _EMPHASIS_RE.sub("", raw).strip()
        if not line:
            if lines_out and lines_out[-1] != "":
                lines_out.append("")
            continue
        if _META_LINE_RE.match(line):
            continue
        cleaned = _HASHTAG_RE.sub(" ", line).strip()
        if not cleaned or cleaned.startswith("#"):
            continue
        lines_out.append(cleaned)
    # Collapse excess blank lines.
    joined = "\n".join(lines_out)
    return re.sub(r"\n{3,}", "\n\n", joined).strip() + ("\n" if joined.strip() else "")
