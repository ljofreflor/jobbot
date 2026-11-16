"""Turn a public bases PDF into one posting. No OCR, no stored bytes."""

from __future__ import annotations

import hashlib
import re
import unicodedata
import urllib.error
import urllib.request
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from jobbot.companies.urls import request_url
from jobbot.jobs.closure import closure_evidence
from jobbot.models.job import JobPosting
from jobbot.pdf_text import PdfTextError, text_from_pdf_bytes

_MAX_BYTES = 20 * 1024 * 1024
_MIN_USEFUL = 200
_SANTIAGO = ZoneInfo("America/Santiago")
_MONTHS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}
# Tried in order: the first lead that dates the application period wins, so a later
# timeline (contrato, resultados, consultas) never becomes the deadline.
_LEADS = (
    "plazo de postulacion",
    "recepcion de antecedentes",
    "fecha de cierre",
)
# "hasta el <fecha>" closes many timelines; it is the deadline only when the words
# before it are about receiving applications.
_UNTIL = "hasta el"
_APPLY_WORDS = ("postulacion", "postular", "antecedentes")
_WINDOW = 96
_DATE = re.compile(r"(\d{1,2}) de ([a-z]+) de (\d{4})")
# Bases almost always reserve the right to declare the contest deserted ("podrá ser
# declarado desierto"); only a declaration already made closes it.
_DESERTED = re.compile(
    r"(?:fue|fueron|ha\s+sido|han\s+sido|queda|quedo|se\s+declara|se\s+declaro)\s+"
    r"(?:declarad[oa]s?\s+)?desiert[oa]s?\b"
)
_ORG = re.compile(
    r"((?:Ilustre\s+)?Municipalidad\s+de\s+\S+"
    r"|Corporaci[oó]n\s+Municipal\s+\S+"
    r"|Departamento\s+de\s+Salud\s+\S+)",
    re.IGNORECASE,
)
_TITLE_TOKENS = ("cargo", "concurso", "llamado a")
_TRACKING = ("utm_", "fbclid", "gclid", "mc_eid")


class NotAPdf(Exception):
    """The response is not a PDF; another add path may handle the URL."""


class PdfAddError(Exception):
    """A PDF URL was recognised and then refused."""


class PdfNoText(PdfAddError):
    """No usable text layer."""


class PdfClosed(PdfAddError):
    """The document says the contest is already gone."""


class PdfFetchError(PdfAddError):
    """The host did not return the file."""


class PdfBlocked(PdfAddError):
    """robots.txt says not to download it."""


@dataclass(frozen=True)
class PublicBody:
    """One public response. `final_url` is where redirects landed."""

    status: int
    body: bytes
    content_type: str
    final_url: str


@dataclass(frozen=True)
class PdfDraft:
    """A posting ready to store, plus whether its closing date is missing."""

    job: JobPosting
    unverified: bool


def fetch_public(url: str) -> PublicBody:
    """Download a public URL after robots.txt. Tests replace this."""
    from jobbot.companies.oneshot import RobotsPolicy, RobotsVerdict, UrllibFetcher
    from jobbot.portals.detect import ROBOTS_DISALLOWED_KINDS, detect_ats

    if detect_ats(url) in ROBOTS_DISALLOWED_KINDS:
        raise PdfBlocked(
            f"{urlsplit(url).netloc} pide a los robots no leerlo (robots.txt: Disallow: /), "
            "así que JobBot no lo descarga. Abre la página, guarda el documento y usa "
            f"`jobbot jobs add --file ficha.txt --url {url}`."
        )
    try:
        wire = request_url(url)
    except ValueError as exc:
        raise PdfFetchError(f"no se puede pedir esta URL: {exc}") from exc
    policy = RobotsPolicy(UrllibFetcher(delay=0))
    verdict = policy.verdict(wire)
    if verdict is RobotsVerdict.DISALLOWED:
        raise PdfBlocked("robots.txt no permite esta URL. Copia el PDF y usa jobs add --file.")
    if verdict is RobotsVerdict.HOST_REFUSED:
        raise PdfFetchError("el sitio no entregó robots.txt")
    request = urllib.request.Request(wire, headers={"User-Agent": "jobbot"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:  # noqa: S310
            status = int(getattr(response, "status", 200))
            content_type = str(response.headers.get("Content-Type", ""))
            final = str(response.geturl())
            body = response.read(_MAX_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise PdfFetchError(f"HTTP {exc.code}") from exc
    except OSError as exc:
        raise PdfFetchError(str(exc)) from exc
    if status != 200:
        raise PdfFetchError(f"HTTP {status}")
    if len(body) > _MAX_BYTES:
        raise PdfFetchError("el PDF supera 20 MB")
    return PublicBody(status=status, body=body, content_type=content_type, final_url=final)


def looks_like_pdf(content_type: str, body: bytes) -> bool:
    """`application/pdf`, or any type whose body starts with the PDF magic."""
    kind = content_type.split(";", 1)[0].strip().casefold()
    if kind == "application/pdf":
        return True
    return body.startswith(b"%PDF")


def posting_identity(url: str) -> str:
    """SHA-256 of the URL with the fragment and tracking parameters removed."""
    parts = urlsplit(url.strip())
    kept = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.casefold().startswith(_TRACKING)
    ]
    query = "&".join(f"{key}={value}" for key, value in kept)
    clean = urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))
    return hashlib.sha256(clean.encode()).hexdigest()


def job_from_public(url: str) -> PdfDraft:
    """Fetch `url` and build one posting, or raise when it must not be stored."""
    return job_from_body(fetch_public(url))


def job_from_body(fetched: PublicBody) -> PdfDraft:
    """Build one posting from an already downloaded body."""
    if not looks_like_pdf(fetched.content_type, fetched.body):
        raise NotAPdf(fetched.final_url)
    try:
        text = text_from_pdf_bytes(fetched.body)
    except PdfTextError as exc:
        raise PdfAddError(str(exc)) from exc
    if _useful(text) < _MIN_USEFUL:
        raise PdfNoText("el PDF no tiene capa de texto. Usa jobs add --file.")
    if _deserted(text):
        raise PdfClosed("No se guarda: concurso declarado desierto.")
    closing = _closing(text)
    title = _title(text, fetched.final_url)
    company, location = _organization(text, fetched.final_url)
    job = JobPosting(
        id="pending",
        source="pdf",
        source_job_id=posting_identity(fetched.final_url),
        url=fetched.final_url,
        title=title,
        company=company,
        location=location,
        description=text,
        raw_description=text,
        closes_at=closing[0] if closing else None,
        closes_on=closing[0].date() if closing else None,
        closes_text=closing[1] if closing else None,
    )
    return PdfDraft(job=job, unverified=closing is None)


def _useful(text: str) -> int:
    return sum(1 for char in text if char.isalnum())


def _fold(text: str) -> str:
    stripped = unicodedata.normalize("NFKD", text or "")
    return "".join(char for char in stripped if not unicodedata.combining(char)).casefold()


def _deserted(text: str) -> bool:
    if _DESERTED.search(_fold(text)) is not None:
        return True
    return closure_evidence(text) is not None


def _closing(text: str) -> tuple[datetime, str] | None:
    folded = _fold(text)
    for lead in _LEADS:
        for at in _occurrences(folded, lead):
            dated = _period_end(folded[at : at + _WINDOW])
            if dated is not None:
                return _moment(dated)
    for at in _occurrences(folded, _UNTIL):
        before = folded[max(0, at - _WINDOW) : at]
        if any(word in before for word in _APPLY_WORDS):
            dated = _period_end(folded[at : at + _WINDOW])
            if dated is not None:
                return _moment(dated)
    return None


def _occurrences(folded: str, needle: str) -> Iterator[int]:
    start = 0
    while True:
        at = folded.find(needle, start)
        if at < 0:
            return
        yield at
        start = at + len(needle)


def _period_end(window: str) -> tuple[date, str] | None:
    """The day the period closes: what follows "hasta", else the first date written."""
    at = window.find("hasta")
    if at >= 0:
        after = _dates_in(window[at:])
        if after:
            return after[0]
    dates = _dates_in(window)
    return dates[0] if dates else None


def _dates_in(window: str) -> list[tuple[date, str]]:
    found: list[tuple[date, str]] = []
    for match in _DATE.finditer(window):
        month = _MONTHS.get(match.group(2))
        if month is None:
            continue
        try:
            when = date(int(match.group(3)), month, int(match.group(1)))
        except ValueError:
            continue
        found.append((when, match.group(0)))
    return found


def _moment(dated: tuple[date, str]) -> tuple[datetime, str]:
    when, evidence = dated
    moment = datetime(when.year, when.month, when.day, 23, 59, 59, tzinfo=_SANTIAGO)
    return moment, evidence


def _title(text: str, url: str) -> str:
    for line in text.splitlines()[:40]:
        folded = _fold(line)
        if any(token in folded for token in _TITLE_TOKENS):
            cleaned = " ".join(line.split())
            if cleaned:
                return cleaned[:180]
    stem = Path(urlsplit(url).path).stem or "bases"
    return stem[:180]


def _organization(text: str, url: str) -> tuple[str, str | None]:
    found = _ORG.search(text)
    if found is None:
        host = urlsplit(url).netloc or "pdf"
        return host, None
    name = " ".join(found.group(1).split())
    place = name.split()[-1]
    return name[:180], place[:80]
