"""A rejection is a preference, a condition, or a missing fact. Only the last may edit."""

from __future__ import annotations

_PREFERENCE = (
    "no quiero",
    "no me interesa",
    "prefer not",
    "do not want",
    "don't want",
)
_CONDITIONS = (
    "jornada",
    "modalidad",
    "ubicacion",
    "ubicación",
    "sueldo",
    "schedule",
    "commute",
)
_EXPERIENCE = (
    "no tengo",
    "no cuento con",
    "sin experiencia",
    "i do not have",
    "i don't have",
)


def rejection_kind(text: str) -> str:
    """Preference wins over conditions, and conditions over a missing fact."""
    folded = (text or "").casefold()
    if any(phrase in folded for phrase in _PREFERENCE):
        return "preference"
    if any(phrase in folded for phrase in _CONDITIONS):
        return "conditions"
    if any(phrase in folded for phrase in _EXPERIENCE):
        return "experience"
    return "unclear"


def may_edit_profile(kind: str) -> bool:
    """A preference or a working condition is not a missing skill."""
    return kind == "experience"
