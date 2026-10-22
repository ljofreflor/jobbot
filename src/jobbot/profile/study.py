"""A repeated market term the profile lacks is a study question, not a new skill."""

from __future__ import annotations


def study_question(term: str, *, repeats: int, known: bool) -> str:
    """The question, or why there is nothing to ask. Never a skill to add."""
    cleaned = term.strip()
    if not cleaned:
        raise ValueError("missing term")
    if repeats < 0:
        raise ValueError("repeats must be >= 0")
    if known:
        return "already in the profile"
    if repeats < 2:
        return "not repeated"
    return f"pregunta: estudias {cleaned}?"
