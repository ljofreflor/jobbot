"""Map one Greenhouse job. No network."""

from __future__ import annotations

import re
from datetime import datetime
from html import unescape
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from bs4 import BeautifulSoup

from jobbot.companies.discovery import career_root_url
from jobbot.jobs.normalization import fold_text
from jobbot.models.job import JobPosting
from jobbot.portals.detect import AtsKind

_TOKEN = re.compile(r"^[A-Za-z0-9_-]+$")
_TRACKING = ("utm_", "fbclid", "gclid", "mc_eid")


def board_token(raw: str) -> str:
    """Bare token, or the first path segment of a Greenhouse board URL."""
    text = raw.strip()
    if "://" not in text and "." not in text:
        if "/" in text or _TOKEN.fullmatch(text) is None:
            msg = f"{raw} is not a Greenhouse board token"
            raise ValueError(msg)
        return text
    else:
        rooted = career_root_url(
            text if "://" in text else f"https://{text}",
            AtsKind.GREENHOUSE,
        )
        token = urlsplit(rooted).path.strip("/").split("/")[0]
    if _TOKEN.fullmatch(token) is None:
        msg = f"{raw} is not a Greenhouse board token"
        raise ValueError(msg)
    return token


def public_job_url(url: str) -> str:
    """Drop tracking parameters. Keep ``gh_jid``."""
    parts = urlsplit(url)
    kept = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key == "gh_jid" or not _tracked(key)
    ]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(kept), ""))


def parse_board(payload: dict[str, Any], token: str) -> list[JobPosting] | None:
    """Jobs from a board payload. None when `jobs` is missing."""
    jobs = payload.get("jobs")
    if not isinstance(jobs, list):
        return None
    out: list[JobPosting] = []
    for item in jobs:
        if isinstance(item, dict):
            job = job_from_item(item, token)
            if job is not None:
                out.append(job)
    return out


def job_from_item(item: dict[str, Any], token: str) -> JobPosting | None:
    """One posting. ``content`` may be absent on a list without content."""
    raw_id = item.get("id")
    title = " ".join(str(item.get("title") or "").split())
    if raw_id is None or not title:
        return None
    posting_id = str(raw_id).strip()
    if not posting_id:
        return None
    place = item.get("location")
    location = ""
    if isinstance(place, dict):
        location = str(place.get("name") or "").strip()
    company = str(item.get("company_name") or "").strip() or token
    absolute = str(item.get("absolute_url") or "").strip()
    fallback = f"https://job-boards.greenhouse.io/{token}/jobs/{posting_id}"
    url = public_job_url(absolute) if absolute else fallback
    raw_html, text = _content(item.get("content"))
    return JobPosting(
        id="pending",
        source="greenhouse",
        source_job_id=f"{token}:{posting_id}",
        url=url,
        ats_url=f"https://job-boards.greenhouse.io/{token}/jobs/{posting_id}",
        ats_kind="greenhouse",
        title=title[:180],
        company=company[:180],
        location=location or None,
        remote_type=_remote(location, item.get("offices"), item.get("metadata")),
        description=text[:2000],
        raw_description=raw_html,
        posted_at=_aware(item.get("first_published")),
        closes_at=_aware(item.get("application_deadline")),
    )


def _content(value: object) -> tuple[str, str]:
    if not isinstance(value, str) or not value.strip():
        return "", ""
    raw = unescape(value)
    text = " ".join(BeautifulSoup(raw, "html.parser").get_text(" ", strip=True).split())
    return raw, text


def _aware(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        return None
    return moment


def _remote(location: str, offices: object, metadata: object) -> str | None:
    parts = [location]
    if isinstance(offices, list):
        for office in offices:
            if isinstance(office, dict):
                parts.append(str(office.get("name") or ""))
    if isinstance(metadata, list):
        for entry in metadata:
            if isinstance(entry, dict):
                parts.append(str(entry.get("value") or ""))
    folded = fold_text(" ".join(parts))
    if "remote" in folded or "remoto" in folded:
        return "remote"
    return None


def _tracked(key: str) -> bool:
    return key.startswith(_TRACKING) or key in {"fbclid", "gclid", "mc_eid"}
