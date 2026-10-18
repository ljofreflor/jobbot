"""Map an Oracle Recruiting Cloud requisition. No network."""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from jobbot.jobs.normalization import fold_text
from jobbot.models.job import JobPosting

PAGE_SIZE = 25
_SITE_PATH = re.compile(r"/sites/([^/?#]+)", re.I)
_HOST_SITE = re.compile(r"^([^/\s]+)/([^/\s]+)$")


def parse_site(raw: str) -> tuple[str, str] | None:
    """`(host, siteNumber)` from `host/CX_1` or a Candidate Experience URL."""
    text = raw.strip()
    if "://" not in text and _HOST_SITE.fullmatch(text) and "hcmUI" not in text:
        host, number = text.split("/", 1)
        if "." in host and number:
            return host, number
        return None
    if "://" not in text:
        text = f"https://{text}"
    parts = urlsplit(text)
    found = _SITE_PATH.search(parts.path)
    if parts.hostname and found:
        return parts.hostname, found.group(1)
    return None


def job_url(host: str, site: str, posting_id: str) -> str:
    """Public job page. The language segment stays `en`."""
    return f"https://{host}/hcmUI/CandidateExperience/en/sites/{site}/job/{posting_id}"


def parse_list(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], int] | None:
    """Requisitions and `TotalJobsCount`. None when the list shape changed."""
    items = payload.get("items")
    if not isinstance(items, list) or not items or not isinstance(items[0], dict):
        return None
    head = items[0]
    rows = head.get("requisitionList")
    total = head.get("TotalJobsCount")
    if not isinstance(rows, list) or not isinstance(total, int):
        return None
    return [row for row in rows if isinstance(row, dict)], total


def job_from_row(
    row: dict[str, Any],
    *,
    host: str,
    site: str,
    company: str | None,
) -> JobPosting | None:
    """One list row. Closing date arrives later, on the detail."""
    raw_id = row.get("Id")
    title = " ".join(str(row.get("Title") or "").split())
    if raw_id is None or not title:
        return None
    posting_id = str(raw_id).strip()
    if not posting_id:
        return None
    org = str(row.get("Organization") or "").strip()
    name = (company or org or host)[:180]
    location = str(row.get("PrimaryLocation") or "").strip() or None
    url = job_url(host, site, posting_id)
    summary = str(row.get("ShortDescriptionStr") or "").strip()
    return JobPosting(
        id="pending",
        source="oracle_orc",
        source_job_id=f"{host}/{site}:{posting_id}",
        url=url,
        ats_url=url,
        ats_kind="oracle",
        title=title[:180],
        company=name,
        location=location,
        remote_type=_remote(row, location or ""),
        employment_type=_employment(row),
        description=summary[:2000],
        posted_at=_posted(row.get("PostedDate")),
        closes_at=None,
    )


def apply_detail(job: JobPosting, payload: dict[str, Any]) -> JobPosting:
    """Fill closing date and the longer description from the detail payload."""
    items = payload.get("items")
    head = items[0] if isinstance(items, list) and items and isinstance(items[0], dict) else payload
    if not isinstance(head, dict):
        return job
    end = _aware(head.get("ExternalPostedEndDate"))
    start = _aware(head.get("ExternalPostedStartDate"))
    longer = head.get("ExternalDescription") or head.get("Description")
    text = str(longer).strip() if isinstance(longer, str) else ""
    return job.model_copy(
        update={
            "closes_at": end or job.closes_at,
            "posted_at": start or job.posted_at,
            "description": (text or job.description)[:2000],
        }
    )


def _remote(row: dict[str, Any], location: str) -> str | None:
    code = str(row.get("WorkplaceTypeCode") or "")
    label = str(row.get("WorkplaceType") or "")
    blob = fold_text(f"{code} {label} {location}")
    if "remote" in blob or "remoto" in blob or "home-based" in blob or "home based" in blob:
        return "remote"
    if "hybrid" in blob or "hibrido" in blob:
        return "hybrid"
    return None


def _employment(row: dict[str, Any]) -> str | None:
    raw = row.get("ContractType") or row.get("JobSchedule")
    text = str(raw).strip() if raw else ""
    return text or None


def _posted(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    aware = _aware(value)
    if aware is not None:
        return aware
    try:
        day = datetime.strptime(value.strip(), "%Y-%m-%d")
    except ValueError:
        return None
    return day.replace(tzinfo=UTC)


def _aware(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if "T" not in text:
        return None
    try:
        moment = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        return None
    return moment
