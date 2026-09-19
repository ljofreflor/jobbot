"""LaTeX escaping helpers."""

from __future__ import annotations

import re

_LATEX_SPECIALS = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}

_ESCAPE_RE = re.compile(
    "|".join(re.escape(k) for k in sorted(_LATEX_SPECIALS, key=len, reverse=True))
)


def escape_latex(text: str) -> str:
    """Escape characters that are special in LaTeX text mode."""
    return _ESCAPE_RE.sub(lambda m: _LATEX_SPECIALS[m.group(0)], text)


def escape_latex_multiline(text: str) -> str:
    """Escape LaTeX and normalize whitespace for paragraph fields."""
    cleaned = " ".join(text.split())
    return escape_latex(cleaned)
