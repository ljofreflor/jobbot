"""A silence follow-up is a draft. It is never sent, and two is the cap."""

from __future__ import annotations

_CAP = 2


def followup_draft(company: str, title: str, *, sent: int) -> str | None:
    """The draft, or None when ``sent`` already reached the cap.

    Raises ValueError when ``sent`` is negative or a fact is blank. The text
    uses only the company and the title that were passed in.
    """
    if sent < 0:
        raise ValueError("sent must be >= 0")
    if sent >= _CAP:
        return None
    company_name = company.strip()
    role = title.strip()
    if not company_name or not role:
        raise ValueError("missing fact")
    return f"Escribo por {role} en {company_name}. Sigo disponible si hay novedades."
