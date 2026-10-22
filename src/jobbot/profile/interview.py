"""One interview question about a gap. The answer is not invented."""

from __future__ import annotations


def gap_question(gap: str) -> str:
    """The question. A blank gap is refused. No answer is attached."""
    cleaned = gap.strip()
    if not cleaned:
        raise ValueError("missing gap")
    return f"pregunta: ¿qué evidencia hay de {cleaned}?"
