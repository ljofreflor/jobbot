"""Saved Alta Dirección Pública ficha. The site's robots.txt forbids fetching it."""

from __future__ import annotations

import re
import unicodedata

from bs4 import BeautifulSoup

from jobbot.jobs.closing import find_closing
from jobbot.models.job import JobPosting
from jobbot.portals.detect import AtsKind

_CODE = re.compile(r"ADP-\d+", re.IGNORECASE)
_SKIP = ("fecha de cierre", "renta", "region", "codigo", "ministerio")


class AdpParseError(ValueError):
    """The saved page has no title or no service name."""


def parse_ficha(html: str, *, url: str) -> JobPosting:
    """Offline ficha: title, service, requirements, rent line and Chile closing."""
    soup = BeautifulSoup(html or "", "html.parser")
    heading = soup.find("h1")
    title = heading.get_text(" ", strip=True) if heading is not None else ""
    if not title:
        raise AdpParseError("saved ADP ficha has no h1")

    company = ""
    location: str | None = None
    rent: str | None = None
    for paragraph in soup.find_all("p"):
        text = paragraph.get_text(" ", strip=True)
        if not text:
            continue
        folded = _fold(text)
        if folded.startswith("renta"):
            rent = text
            continue
        if folded.startswith("region"):
            location = text
            continue
        if folded.startswith(_SKIP):
            continue
        if not company:
            company = text
    if not company:
        raise AdpParseError("saved ADP ficha has no service name")

    code = _CODE.search(url)
    closing = find_closing(soup.get_text("\n", strip=True))
    requirements = [
        item.get_text(" ", strip=True)
        for item in soup.find_all("li")
        if item.get_text(strip=True)
    ]
    description = soup.get_text("\n", strip=True)
    return JobPosting(
        id="pending",
        source=AtsKind.ALTA_DIRECCION_PUBLICA.value,
        source_job_id=code.group(0).upper() if code else None,
        url=url,
        title=title,
        company=company,
        location=location,
        description=description,
        raw_description=description,
        requirements=requirements,
        ats_url=url,
        ats_kind=AtsKind.ALTA_DIRECCION_PUBLICA.value,
        note=rent,
        closes_at=closing.at if closing else None,
        closes_on=closing.on if closing else None,
        closes_text=closing.text if closing else None,
    )


def _fold(text: str) -> str:
    stripped = unicodedata.normalize("NFKD", text)
    plain = "".join(ch for ch in stripped if not unicodedata.combining(ch)).casefold()
    return " ".join(plain.split())
