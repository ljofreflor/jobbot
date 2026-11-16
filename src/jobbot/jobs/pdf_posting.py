"""Turn a public bases PDF into one posting. No OCR, no stored bytes."""

from __future__ import annotations

import hashlib
import re
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

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
_LEADS = (
    "plazo de postulacion",
    "recepcion de antecedentes",
    "fecha de cierre",
    "hasta el",
)
_DATE = re.compile(r"(\d{1,2}) de ([a-z]+) de (\d{4})")
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

    policy = RobotsPolicy(UrllibFetcher(delay=0))
    verdict = policy.verdict(url)
    if verdict is RobotsVerdict.DISALLOWED:
        raise PdfBlocked("robots.txt no permite esta URL. Copia el PDF y usa jobs add --file.")
    if verdict is RobotsVerdict.HOST_REFUSED:
        raise PdfFetchError("el sitio no entregó robots.txt")
    request = urllib.request.Request(url, headers={"User-Agent": "jobbot"})
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
    if "declarado desierto" in _fold(text):
        return True
    return closure_evidence(text) is not None


def _closing(text: str) -> tuple[datetime, str] | None:
    folded = _fold(text)
    found: list[date] = []
    evidence = ""
    for lead in _LEADS:
        start = 0
        while True:
            at = folded.find(lead, start)
            if at < 0:
                break
            window = folded[at : at + 96]
            match = _DATE.search(window)
            if match is not None:
                month = _MONTHS.get(match.group(2))
                if month is not None:
                    try:
                        when = date(int(match.group(3)), month, int(match.group(1)))
                    except ValueError:
                        when = None
                    if when is not None:
                        found.append(when)
                        evidence = match.group(0)
            start = at + len(lead)
    if not found:
        return None
    latest = max(found)
    moment = datetime(latest.year, latest.month, latest.day, 23, 59, 59, tzinfo=_SANTIAGO)
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
