"""Map one `buscarListas` page. No network."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from jobbot.models.job import JobPosting

PAGE_SIZE = 50
SANTIAGO = ZoneInfo("America/Santiago")
OFFER = "https://www.bne.cl/oferta"
CONFIDENTIAL = "Confidencial"


@dataclass
class SearchPage:
    """One parsed page, or a shape change."""

    jobs: list[JobPosting]
    total: int
    active: int
    pages: int
    echoed: str
    changed: bool
    detail: str


def search_url(query: str, page: int) -> str:
    """Public list. Spaces stay `%20`."""
    from urllib.parse import quote

    text = quote(query, safe="")
    return (
        "https://www.bne.cl/data/ofertas/buscarListas"
        f"?mostrar=empleo&textoLibre={text}"
        f"&numPaginaRecuperar={page}&numResultadosPorPagina={PAGE_SIZE}"
        "&clasificarYPaginar=true"
    )


def parse_page(payload: Any) -> SearchPage:
    """Read totals and rows. A missing list is a shape change."""
    if not isinstance(payload, dict):
        return _changed("la respuesta no es un objeto")
    total = payload.get("numResultadosTotal")
    page = payload.get("paginaOfertas")
    rows = page.get("resultados") if isinstance(page, dict) else None
    if not isinstance(total, int) or not isinstance(rows, list):
        return _changed("faltan paginaOfertas, resultados o numResultadosTotal")
    active = payload.get("totalOfertasActivas")
    pages = payload.get("numPaginasTotal")
    echoed = payload.get("textoLibre")
    jobs: list[JobPosting] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            return _changed("una fila no es un objeto")
        job = job_from_row(row)
        if job is None or job.source_job_id in seen:
            continue
        seen.add(job.source_job_id or "")
        jobs.append(job)
    return SearchPage(
        jobs=jobs,
        total=total,
        active=active if isinstance(active, int) else -1,
        pages=pages if isinstance(pages, int) and pages > 0 else 1,
        echoed=echoed if isinstance(echoed, str) else "",
        changed=False,
        detail="",
    )


def job_from_row(row: dict[str, Any]) -> JobPosting | None:
    """One result. A hidden employer is `Confidencial`."""
    code = str(row.get("codigo") or "").strip()
    title = str(row.get("titulo") or "").strip()
    if not code or not title:
        return None
    shown = row.get("mostrarEmpresa")
    employer = str(row.get("empresa") or "").strip()
    hidden = shown is False or employer.casefold() == CONFIDENTIAL.casefold()
    company = CONFIDENTIAL if hidden or not employer else employer
    place = str(row.get("comuna") or "").strip()
    region = str(row.get("region") or "").strip()
    location = ", ".join(part for part in (place, region, "Chile") if part)
    origin = str(row.get("origen") or "").strip()
    note = origin if origin and origin.upper() != "WEB" else None
    return JobPosting(
        id="pending",
        source="bne",
        source_job_id=code,
        url=f"{OFFER}/{code}",
        ats_url=f"{OFFER}/{code}",
        ats_kind="bne",
        title=title[:180],
        company=company[:180],
        location=location[:180] or "Chile",
        description=title[:2000],
        posted_at=_posted(str(row.get("fecha") or "")),
        closes_at=None,
        note=note,
    )


def _posted(text: str) -> datetime | None:
    parts = text.split("/")
    if len(parts) != 3:
        return None
    try:
        day, month, year = (int(part) for part in parts)
    except ValueError:
        return None
    if year < 100:
        year += 2000
    try:
        return datetime(year, month, day, tzinfo=SANTIAGO)
    except ValueError:
        return None


def _changed(detail: str) -> SearchPage:
    return SearchPage(
        jobs=[],
        total=0,
        active=0,
        pages=0,
        echoed="",
        changed=True,
        detail=detail,
    )
