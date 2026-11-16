"""Read the embedded GeneXus grid. No network."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from html import unescape
from zoneinfo import ZoneInfo

from bs4 import BeautifulSoup, Tag

from jobbot.models.job import JobPosting

LISTING = (
    "https://postulaciones.pjud.cl/concursos/servlet/com.postulaciones.concursosenpostulacion"
)
SANTIAGO = ZoneInfo("America/Santiago")
COLUMNS = 29
_DATE = re.compile(r"\d{2}/\d{2}/\d{4}")
_PRIMARY = re.compile(r"PR\d*", re.I)
_HOUR_NOTE = "hora no publicada"
_PRIMARY_NOTE = "escalafón primario: requiere carrera judicial"

# Column indexes observed on the public grid.
_LADDER = 1
_NUMBER = 6
_TITLE = 9
_PLACE = 10
_COURT = 11
_OPENS = 12
_CLOSES = 13
_ORG = 15


@dataclass
class GridPage:
    """One listing parse."""

    jobs: list[JobPosting]
    changed: bool
    detail: str


def parse_grid(html: str) -> GridPage:
    """Map `GridContainerDataV` into postings, or report a shape change."""
    raw = _grid_value(html)
    if raw is None:
        return GridPage(jobs=[], changed=True, detail="falta GridContainerDataV")
    try:
        rows = json.loads(unescape(raw))
    except json.JSONDecodeError:
        return GridPage(jobs=[], changed=True, detail="GridContainerDataV no es JSON")
    if not isinstance(rows, list):
        return GridPage(jobs=[], changed=True, detail="GridContainerDataV no es una grilla")
    jobs: list[JobPosting] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, list) or len(row) != COLUMNS:
            return GridPage(jobs=[], changed=True, detail="una fila no tiene 29 columnas")
        cells = ["" if cell is None else str(cell).strip() for cell in row]
        opened = _moment(cells[_OPENS], end=False)
        closed = _moment(cells[_CLOSES], end=True)
        if opened is None or closed is None:
            return GridPage(jobs=[], changed=True, detail="una fecha no es dd/mm/aaaa")
        number = cells[_NUMBER]
        if not number or number in seen:
            continue
        seen.add(number)
        ladder = cells[_LADDER]
        title = cells[_TITLE] or number
        court = cells[_COURT]
        org = cells[_ORG]
        company = f"{org} — {court}" if org and court else (org or court or "pjud")
        place = cells[_PLACE]
        location = f"{place}, Chile" if place else "Chile"
        notes = [_HOUR_NOTE]
        if _PRIMARY.fullmatch(ladder):
            notes.append(_PRIMARY_NOTE)
        jobs.append(
            JobPosting(
                id="pending",
                source="pjud",
                source_job_id=number,
                url=f"{LISTING}#concurso-{number}",
                ats_url=f"{LISTING}#concurso-{number}",
                ats_kind="pjud",
                title=f"{title} ({number})"[:180],
                company=company[:180],
                location=location[:180],
                seniority=ladder or None,
                description=title[:2000],
                posted_at=opened,
                closes_at=closed,
                note="; ".join(notes),
            )
        )
    return GridPage(jobs=jobs, changed=False, detail="")


def _grid_value(html: str) -> str | None:
    soup = BeautifulSoup(html or "", "html.parser")
    node = soup.find("input", attrs={"name": "GridContainerDataV"})
    if not isinstance(node, Tag):
        node = soup.find("input", id="GridContainerDataV")
    if not isinstance(node, Tag):
        return None
    value = node.get("value")
    if not isinstance(value, str) or not value.strip():
        return None
    return value


def _moment(text: str, *, end: bool) -> datetime | None:
    if _DATE.fullmatch(text) is None:
        return None
    try:
        day = datetime.strptime(text, "%d/%m/%Y")
    except ValueError:
        return None
    clock = (23, 59, 59) if end else (0, 0, 0)
    return datetime(day.year, day.month, day.day, *clock, tzinfo=SANTIAGO)
