"""Map one Ready careers JSON payload. No network."""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import quote, urlsplit

from bs4 import BeautifulSoup

from jobbot.jobs.normalization import fold_text
from jobbot.models.job import JobPosting

GATEWAY = "https://ready-ats-gateway-prod-76bcavjo.uc.gateway.dev/api/v1/careers"
_CAREER = re.compile(r"^/careers/(?P<slug>[^/]+)/?$")
COMPANY = "Ready"


def career_slug(url: str) -> str | None:
    """`/careers/{slug}` on a Ready host, or None."""
    path = urlsplit(url.strip()).path
    found = _CAREER.match(path)
    return found.group("slug") if found else None


def canonical_url(url: str) -> str | None:
    """Drop the query. The saved link is the careers path."""
    parsed = urlsplit(url.strip())
    slug = career_slug(url)
    if not parsed.hostname or slug is None:
        return None
    return f"https://{parsed.hostname}/careers/{slug}"


def api_url(slug: str) -> str:
    """Public careers JSON. No frontend key."""
    return f"{GATEWAY}/{quote(slug, safe='')}"


def job_from_payload(payload: Any, *, page_url: str) -> JobPosting | None:
    """One posting. A missing title or description is a shape change."""
    if not isinstance(payload, dict):
        return None
    title = str(payload.get("nombreVacante") or "").strip()
    raw_html = payload.get("descripcionVacante")
    if not title or not isinstance(raw_html, str) or not raw_html.strip():
        return None
    description = BeautifulSoup(raw_html, "html.parser").get_text(" ", strip=True)
    if not description:
        return None
    link = canonical_url(page_url)
    if link is None:
        return None
    slug = career_slug(page_url) or ""
    posting_id = payload.get("idVacante")
    source_id = str(posting_id).strip() if posting_id is not None else slug
    place = str(payload.get("paisVacante") or "").strip() or None
    modality = str(payload.get("modalidadVacante") or "")
    remote = "remot" in fold_text(modality)
    seniority = str(payload.get("seniorityVacante") or "").strip() or None
    contract = str(payload.get("tipoContratoVacante") or "").strip() or None
    employer = str(payload.get("nombreEmpresa") or payload.get("empresa") or "").strip()
    return JobPosting(
        id="pending",
        source="ready",
        source_job_id=source_id or None,
        url=link,
        ats_url=link,
        ats_kind="ready",
        title=title[:180],
        company=(employer or COMPANY)[:180],
        location=place,
        description=description[:8000],
        raw_description=raw_html,
        skills=_skills(payload.get("stackTecnologicoVacante")),
        seniority=seniority,
        employment_type=contract,
        remote_type="remote" if remote else None,
    )


def _skills(raw: object) -> list[str]:
    if not isinstance(raw, list):
        return []
    found: list[str] = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            found.append(item.strip())
        elif isinstance(item, dict):
            for key in ("nombre", "name", "skill"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    found.append(value.strip())
                    break
    return found
