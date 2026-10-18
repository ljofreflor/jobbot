"""What a job board itself publishes about a posting still taking applicants.

Pure readers, one per board, over what ``jobs check-open`` already downloaded. Each one
answers only from a field or a line the board prints; when that is missing the answer
is ``unknown``, never a guess. Dates without a time are Chilean calendar days, judged
by ``closing_state`` at the latest end of that day.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from jobbot.jobs.closing import ClosingState, closing_state

TRABAJANDO_API = "https://www.trabajando.cl/api/ofertas/{offer_id}"
_TRABAJANDO_PATH = re.compile(r"^/trabajo/(\d+)(?:-|/|$)")
_CHILETRABAJOS_EXPIRY = re.compile(r"^(\d{4}-\d{2}-\d{2})\b")


class OpenStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Signal:
    status: OpenStatus
    evidence: str
    closes_on: date | None = None


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").casefold()


def _on_host(url: str, domain: str) -> bool:
    host = _host(url)
    return host == domain or host.endswith("." + domain)


def trabajando_offer_id(url: str) -> str | None:
    """``https://www.trabajando.cl/trabajo/6135043-asistente-…`` → ``6135043``."""
    if not _on_host(url, "trabajando.cl"):
        return None
    found = _TRABAJANDO_PATH.match(urlparse(url).path)
    return found.group(1) if found else None


def read_trabajando(payload: Any, *, now: datetime) -> Signal:
    """``/api/ofertas/{id}``: ``estadoOferta`` and ``fechaExpiracionFormatoIngles``."""
    if not isinstance(payload, dict):
        return Signal(OpenStatus.UNKNOWN, "Trabajando: respuesta sin forma de oferta")
    state = str(payload.get("estadoOferta") or "").strip()
    expiry = _iso_day(payload.get("fechaExpiracionFormatoIngles"))
    if not state:
        return Signal(OpenStatus.UNKNOWN, "Trabajando: la oferta no informa estadoOferta")
    if state.upper() != "PUBLICADA":
        return Signal(OpenStatus.CLOSED, f"estadoOferta: {state}", expiry)
    if expiry is None:
        return Signal(OpenStatus.UNKNOWN, "estadoOferta: PUBLICADA sin fecha de expiración")
    if closing_state(None, expiry, now=now) is ClosingState.EXPIRED:
        return Signal(OpenStatus.CLOSED, f"estadoOferta: PUBLICADA, expiró {expiry}", expiry)
    return Signal(OpenStatus.OPEN, f"estadoOferta: PUBLICADA, expira {expiry}", expiry)


def is_chiletrabajos(url: str) -> bool:
    return _on_host(url, "chiletrabajos.cl") and urlparse(url).path.startswith("/trabajo/")


def read_chiletrabajos(html: str, *, now: datetime) -> Signal | None:
    """The detail table's ``Expira`` row (``2026-12-23 (en 75 días)``), or None.

    An expired posting drops that row and shows a banner instead; ``closure.py``
    reads the banner, so a missing row is no answer here.
    """
    soup = BeautifulSoup(html or "", "html.parser")
    for cell in soup.find_all("td"):
        if cell.get_text(strip=True).casefold() != "expira":
            continue
        value = cell.find_next_sibling("td")
        found = _CHILETRABAJOS_EXPIRY.match(value.get_text(" ", strip=True) if value else "")
        if found is None:
            return None
        expiry = date.fromisoformat(found.group(1))
        if closing_state(None, expiry, now=now) is ClosingState.EXPIRED:
            return Signal(OpenStatus.CLOSED, f"Expira: {expiry} (vencido)", expiry)
        return Signal(OpenStatus.OPEN, f"Expira: {expiry}", expiry)
    return None


def _iso_day(raw: object) -> date | None:
    try:
        return date.fromisoformat(str(raw)[:10]) if raw else None
    except ValueError:
        return None
