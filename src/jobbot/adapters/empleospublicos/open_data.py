"""Empleos Públicos convocatorias from the Servicio Civil open-data file.

www.empleospublicos.cl answers 403 to any client that names itself — even for its own
robots.txt — and JobBot does not dress up as a browser to get past that. The same
publisher releases every convocatoria as open data on reporte.serviciocivil.cl
(robots.txt only closes ``/wp-admin/``), refreshed daily, with closing date, gross pay
and the official ficha URL. That file is the live search source. Applicant counts
and selection results ride in the same rows; they are aggregates about other people
and never reach a JobPosting.
"""

from __future__ import annotations

import csv
import io
import logging
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from jobbot.companies.oneshot import Fetcher, FetchResult, RobotsPolicy, RobotsVerdict
from jobbot.jobs.normalization import WordIndex, fold_text
from jobbot.models.job import JobPosting
from jobbot.portals.detect import AtsKind

logger = logging.getLogger("jobbot.empleospublicos.open_data")

OPEN_DATA_URL = (
    "https://reporte.serviciocivil.cl/wp-content/uploads/datasets/eepp_convocatorias.csv"
)
OPEN_DATA_PAGE = "https://reporte.serviciocivil.cl/datos/convocatorias-empleos-publicos/"
SITE_ORIGIN = "https://www.empleospublicos.cl"
FICHA_PATH = "/pub/convocatorias/avisotrabajoficha.aspx"
USER_AGENT = "jobbot/0.1 (local; Servicio Civil open data)"
SANTIAGO = ZoneInfo("America/Santiago")

# The file is ~11 MB today; the cap only guards against a runaway response.
_MAX_BYTES = 64_000_000
_POLITE_DELAY = 1.0

_COL_ID = "ID Convocatoria"
_COL_STARTS = "Fecha Inicio Convocatoria"
_COL_CLOSES = "Fecha Cierre Convocatoria"
_COL_MINISTRY = "Ministerio"
_COL_SERVICE = "Servicio"
_COL_ENTITY = "Entidad"
_COL_AREA = "Área de Trabajo"
_COL_VACANCY_TYPE = "Tipo de Vacante"
_COL_ESTAMENTO = "Estamento"
_COL_TITLE = "Cargo"
_COL_REGION = "Región del Cargo"
_COL_VACANCIES = "Cantidad Vacantes"
_COL_STATE = "Estado"
_COL_SALARY = "Renta Bruta"
_COL_URL = "URL Base"
_COL_KIND = "Tipo postulacion"
_COL_UPDATED = "Fecha_Actualizacion"
_REQUIRED = (_COL_ID, _COL_CLOSES, _COL_SERVICE, _COL_TITLE, _COL_STATE, _COL_URL)

# A convocatoria declared void is not open, whatever its closing date says.
_VOID_STATES = ("desierto", "sin efecto")
_SHORT_WORD = 3
# The file writes 1 (or 0) where the pay is not published, e.g. cargos under medical laws.
_SALARY_PLACEHOLDER_MAX = 1
# "Grado 12 E.U.S.", "grado 15° EUS", "GRADO 7": the public pay scale step, when the
# cargo names it. The file has no column for it.
_GRADE_RE = re.compile(
    r"(?i)\bgrado\s*(\d{1,2})\s*[°º]?(?:\s*(e\.?\s*u\.?\s*[sr])(?![a-z]))?"
)
# Published "refreshed daily"; older than this, recent concursos are missing.
STALE_AFTER = timedelta(days=2)


class OpenDataError(RuntimeError):
    """The open-data file could not be read, or no longer has the expected shape."""


@dataclass(frozen=True)
class Convocatoria:
    """One row of the open-data file, limited to what describes the vacancy."""

    id: str
    title: str
    service: str
    url: str
    state: str
    closes_at: datetime | None
    starts_on: date | None = None
    ministry: str = ""
    entity: str = ""
    region: str = ""
    area: str = ""
    estamento: str = ""
    vacancy_type: str = ""
    vacancies: int | None = None
    gross_salary: int | None = None
    grade: str = ""
    online: bool = True
    updated_at: datetime | None = None

    @property
    def key(self) -> str:
        """One lead per cargo: an ingreso-a-planta concurso lists each cargo under its own ``c``."""
        cargo = (parse_qs(urlparse(self.url).query).get("c") or [""])[0]
        return f"{self.id}-{cargo}" if cargo.isdigit() else self.id

    def is_open(self, now: datetime) -> bool:
        if self.closes_at is None:
            return False
        if any(word in fold_text(self.state) for word in _VOID_STATES):
            return False
        return self.closes_at >= now


@dataclass
class OpenDataFetcher:
    """One identifiable GET at a time; no browser headers, no retries around a refusal."""

    timeout: float = 120.0
    max_bytes: int = _MAX_BYTES

    def fetch(self, url: str) -> FetchResult:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": USER_AGENT, "Accept": "text/csv, text/plain"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as resp:  # noqa: S310
                body = resp.read(self.max_bytes)
                if len(body) >= self.max_bytes:
                    logger.warning("Open data truncated at %s bytes: %s", self.max_bytes, url)
                    body = body[: body.rfind(b"\n") + 1]
                return FetchResult(
                    url=resp.geturl() or url,
                    status=int(resp.status),
                    html=body.decode("utf-8-sig", errors="replace"),
                )
        except urllib.error.HTTPError as exc:
            return FetchResult(url=url, status=int(exc.code))
        except OSError as exc:
            logger.debug("Open data fetch failed for %s: %s", url, exc)
            return FetchResult(url=url, status=0)


def download_open_data(
    fetcher: Fetcher | None = None,
    *,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> str:
    """robots.txt first, then the file. A refusal is reported, never worked around."""
    client = fetcher or OpenDataFetcher()
    verdict = RobotsPolicy(client, user_agent=USER_AGENT).verdict(OPEN_DATA_URL)
    if verdict is RobotsVerdict.DISALLOWED:
        msg = f"robots.txt of {urlparse(OPEN_DATA_URL).netloc} disallows the open-data file"
        raise OpenDataError(msg)
    if verdict is RobotsVerdict.HOST_REFUSED:
        msg = f"{urlparse(OPEN_DATA_URL).netloc} refused to serve its robots.txt"
        raise OpenDataError(msg)
    sleep_fn(_POLITE_DELAY)
    result = client.fetch(OPEN_DATA_URL)
    if not result.ok:
        reason = f"HTTP {result.status}" if result.status else "no connection"
        msg = f"Servicio Civil open data unavailable ({reason}): {OPEN_DATA_URL}"
        raise OpenDataError(msg)
    return result.html


def parse_open_data_csv(text: str) -> list[Convocatoria]:
    """Rows of the open-data CSV. Missing columns mean the publisher changed the file."""
    reader = csv.DictReader(io.StringIO(text.lstrip("\ufeff")))
    header = set(reader.fieldnames or ())
    missing = [column for column in _REQUIRED if column not in header]
    if missing:
        msg = f"open-data CSV lacks columns {missing}; the file format changed"
        raise OpenDataError(msg)
    out: list[Convocatoria] = []
    for row in reader:
        item = _convocatoria(row)
        if item is not None:
            out.append(item)
    return out


def search_convocatorias(
    items: Iterable[Convocatoria],
    query: str,
    *,
    now: datetime | None = None,
    region: str | None = None,
    include_closed: bool = False,
) -> list[Convocatoria]:
    """Open convocatorias whose text carries every word of the query, newest first.

    Words match tolerant of gender and plural ('jurídico' finds 'Jurídica'), so the
    query is the candidate's own wording, never a table of professions.
    """
    moment = now or _now()
    words = [w for w in fold_text(query).split() if len(w) >= _SHORT_WORD]
    region_key = fold_text(region or "")
    hits: list[Convocatoria] = []
    for item in items:
        if not include_closed and not item.is_open(moment):
            continue
        if region_key and region_key not in fold_text(item.region):
            continue
        if words:
            index = WordIndex(set(fold_text(_haystack(item)).split()))
            if not all(index.has(word) for word in words):
                continue
        hits.append(item)
    hits.sort(key=lambda c: (c.starts_on or date.min, c.id), reverse=True)
    return hits


def job_from_convocatoria(item: Convocatoria) -> JobPosting:
    """A lead with the facts the file states; the ficha holds the full profile."""
    text = _description(item)
    posted = (
        datetime.combine(item.starts_on, datetime.min.time(), tzinfo=SANTIAGO)
        if item.starts_on
        else None
    )
    return JobPosting(
        id="PENDING",
        source="empleos_publicos",
        source_job_id=item.key,
        url=item.url,
        title=item.title,
        company=item.service,
        location=item.region or None,
        description=text,
        raw_description=text,
        employment_type=item.vacancy_type or None,
        ats_url=item.url,
        ats_kind=AtsKind.EMPLEOS_PUBLICOS.value,
        posted_at=posted,
        note=(
            "empleos publicos: open data lead (Servicio Civil), open the ficha for the profile"
            + ("" if item.gross_salary else "; renta no informada")
        ),
    )


def data_as_of(items: Iterable[Convocatoria]) -> date | None:
    """Day of the newest refresh the file records (``Fecha_Actualizacion``)."""
    stamps = [item.updated_at for item in items if item.updated_at is not None]
    return max(stamps).date() if stamps else None


def staleness_warning(as_of: date | None, *, today: date | None = None) -> str | None:
    """Say so when the file stopped refreshing: newer concursos are simply not in it."""
    if as_of is None:
        return None
    age = (today or _now().date()) - as_of
    if age < STALE_AFTER:
        return None
    return (
        f"Servicio Civil open data was last refreshed on {as_of:%Y-%m-%d} "
        f"({age.days} days ago): concursos published since then are missing. "
        "Check www.empleospublicos.cl in your browser for the newest ones."
    )


@dataclass
class OpenDataCache:
    """Download once per run: every profile query filters the same file.

    A failed download is remembered too, so a refusing host is asked once, not once
    per query.
    """

    fetcher: Fetcher | None = None
    sleep_fn: Callable[[float], None] = time.sleep
    _items: list[Convocatoria] | None = field(default=None, repr=False)
    _error: OpenDataError | None = field(default=None, repr=False)

    def items(self) -> list[Convocatoria]:
        if self._error is not None:
            raise self._error
        if self._items is None:
            try:
                self._items = parse_open_data_csv(
                    download_open_data(self.fetcher, sleep_fn=self.sleep_fn)
                )
            except OpenDataError as exc:
                self._error = exc
                raise
        return self._items


def _now() -> datetime:
    return datetime.now(SANTIAGO)


def _convocatoria(row: dict[str, str]) -> Convocatoria | None:
    def cell(name: str) -> str:
        return str(row.get(name) or "").strip()

    ident, title, service, url = cell(_COL_ID), cell(_COL_TITLE), cell(_COL_SERVICE), cell(_COL_URL)
    if not ident or not title or not service:
        return None
    return Convocatoria(
        id=ident,
        title=title,
        service=service,
        url=_ficha_url(url, ident),
        state=cell(_COL_STATE),
        closes_at=_parse_datetime(cell(_COL_CLOSES)),
        starts_on=_parse_date(cell(_COL_STARTS)),
        ministry=cell(_COL_MINISTRY),
        entity=cell(_COL_ENTITY),
        region=cell(_COL_REGION),
        area=cell(_COL_AREA),
        estamento=cell(_COL_ESTAMENTO),
        vacancy_type=cell(_COL_VACANCY_TYPE),
        vacancies=_parse_int(cell(_COL_VACANCIES)),
        gross_salary=_parse_salary(cell(_COL_SALARY)),
        grade=_grade(title),
        online="linea" in fold_text(cell(_COL_KIND)) or not cell(_COL_KIND),
        updated_at=_parse_datetime(cell(_COL_UPDATED)),
    )


def _ficha_url(raw: str, ident: str) -> str:
    """Canonical ficha for job notices; other kinds keep the link the file publishes.

    ``convFicha.aspx?…&tipo=avisotrabajoficha`` only frames ``avisotrabajoficha.aspx?i=``,
    the same URL ``jobbot get`` canonicalises to, so both routes store one posting.
    """
    parsed = urlparse(raw)
    host = (parsed.hostname or "").casefold().removeprefix("www.")
    canonical = f"{SITE_ORIGIN}{FICHA_PATH}?i={ident}"
    if not raw.startswith("https://") or host != "empleospublicos.cl":
        return canonical
    kind = (parse_qs(parsed.query).get("tipo") or [""])[0].casefold()
    return canonical if kind == "avisotrabajoficha" else raw


def _haystack(item: Convocatoria) -> str:
    return " ".join(
        (item.title, item.service, item.entity, item.ministry, item.area, item.estamento)
    )


def _description(item: Convocatoria) -> str:
    """What the file says, in lines `jobs conditions` already reads (deadline, pay)."""
    lines = [item.title, f"Institución: {item.service}"]
    if item.entity and item.entity != item.service:
        lines.append(f"Entidad: {item.entity}")
    if item.ministry:
        lines.append(f"Ministerio: {item.ministry}")
    if item.region:
        lines.append(f"Región: {item.region}")
    for label, value in (
        ("Estamento", item.estamento),
        ("Grado", item.grade),
        ("Área de trabajo", item.area),
        ("Tipo de vacante", item.vacancy_type),
    ):
        if value:
            lines.append(f"{label}: {value}")
    if item.vacancies:
        lines.append(f"Vacantes: {item.vacancies}")
    if item.closes_at is not None:
        lines.append(f"Fecha límite: {item.closes_at:%Y-%m-%d %H:%M} (hora de Chile)")
    lines.append(
        f"Renta: {format_salary(item.gross_salary)} bruta mensual"
        if item.gross_salary
        else "Renta: no informada en los datos abiertos (ver la ficha)"
    )
    lines.append(
        "Postulación: en línea en Empleos Públicos"
        if item.online
        else "Postulación: aviso, según instrucciones de la ficha"
    )
    lines.append(f"Estado: {item.state}" if item.state else "")
    lines.append(f"Fuente: datos abiertos del Servicio Civil ({OPEN_DATA_PAGE})")
    return "\n".join(line for line in lines if line).strip()


def _parse_datetime(raw: str) -> datetime | None:
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        logger.debug("Unparsable closing date: %s", raw)
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=SANTIAGO)
    return parsed


def _parse_date(raw: str) -> date | None:
    parsed = _parse_datetime(raw)
    return parsed.date() if parsed else None


def format_salary(amount: int) -> str:
    """Chilean pesos as the ficha writes them: ``$2.769.058``."""
    return f"${amount:,}".replace(",", ".")


def _parse_int(raw: str) -> int | None:
    try:
        value = int(float(raw.replace(",", ".")))
    except ValueError:
        return None
    return value if value > 0 else None


def _parse_salary(raw: str) -> int | None:
    """Gross monthly pay; the file's placeholder for 'not published' is never $1."""
    value = _parse_int(raw)
    return value if value is not None and value > _SALARY_PLACEHOLDER_MAX else None


def _grade(title: str) -> str:
    match = _GRADE_RE.search(title)
    if match is None:
        return ""
    scale = re.sub(r"[\s.]", "", match.group(2) or "").upper()
    return f"{int(match.group(1))}°" + (f" {scale}" if scale else "")
