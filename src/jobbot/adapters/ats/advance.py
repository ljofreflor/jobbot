"""An advance label may be pressed later. A submit label never is."""

from __future__ import annotations

import re

_SUBMIT = re.compile(r"\b(enviar|postular|submit|apply)\b", re.IGNORECASE)
_ADVANCE = re.compile(r"\b(siguiente|continuar|next|continue)\b", re.IGNORECASE)


def button_role(label: str) -> str:
    """``submit`` wins when the label also says to advance."""
    if _SUBMIT.search(label or ""):
        return "submit"
    if _ADVANCE.search(label or ""):
        return "advance"
    return "other"


def pressable_advance(labels: list[str]) -> str | None:
    """The first advance label. A submit label is not returned."""
    for label in labels:
        if button_role(label) == "advance":
            return label
    return None
