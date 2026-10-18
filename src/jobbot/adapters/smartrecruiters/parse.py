"""Map one SmartRecruiters posting. No network."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

from jobbot.companies.discovery import career_root_url
from jobbot.jobs.geo import country_name, normalize_country
from jobbot.models.job import JobPosting
from jobbot.portals.detect import AtsKind

PAGE_SIZE = 100


def company_identifier(raw: str) -> str:
    """First path segment of the normalized board URL, or a bare identifier."""
    text = raw.strip()
    if "://" not in text and "/" not in text and "." not in text:
        return text
    rooted = career_root_url(text if "://" in text else f"https://{text}", AtsKind.SMARTRECRUITERS)
    segment = urlsplit(rooted).path.strip("/").split("/")[0]
    return segment


def parse_postings(payload: dict[str, Any], company_id: str) -> tuple[list[JobPosting], int] | None:
    """Postings and `totalFound`. None when the payload is not the public list."""
    if "content" not in payload or "totalFound" not in payload:
        return None
    content = payload["content"]
    total = payload["totalFound"]
    if not isinstance(content, list) or not isinstance(total, int):
        return None
    jobs: list[JobPosting] = []
    for item in content:
        if isinstance(item, dict):
            job = _one(item, company_id)
            if job is not None:
                jobs.append(job)
    return jobs, total


def _one(item: dict[str, Any], company_id: str) -> JobPosting | None:
    posting_id = str(item.get("id") or "").strip()
    title = str(item.get("name") or "").strip()
    if not posting_id or not title:
        return None
    raw_place = item.get("location")
    place: dict[str, Any] = raw_place if isinstance(raw_place, dict) else {}
    city = str(place.get("city") or "").strip()
    country = str(place.get("country") or "").strip()
    code = normalize_country(country)
    label = country_name(code) if code else country
    bits = [bit for bit in (city, label) if bit]
    raw_org = item.get("company")
    org: dict[str, Any] = raw_org if isinstance(raw_org, dict) else {}
    name = str(org.get("name") or "").strip() or company_id
    url = f"https://jobs.smartrecruiters.com/{company_id}/{posting_id}"
    return JobPosting(
        id="pending",
        source="smartrecruiters",
        source_job_id=f"{company_id}:{posting_id}",
        url=url,
        ats_url=url,
        ats_kind="smartrecruiters",
        title=title[:180],
        company=name[:180],
        location=", ".join(bits) or None,
        remote_type="remote" if place.get("remote") is True else None,
        description=title[:2000],
        posted_at=_released(item.get("releasedDate")),
        closes_at=None,
    )


def _released(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if moment.tzinfo is None:
        return None
    return moment
