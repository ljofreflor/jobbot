"""LinkedIn job-search cards, read from saved HTML. Sends nothing."""

from __future__ import annotations

import re
from datetime import datetime

from bs4 import BeautifulSoup, Tag

from jobbot.adapters.linkedin.sweep import posted_at_from_text
from jobbot.models.job import JobPosting

_VIEW = re.compile(r"/jobs/view/(\d+)")
_INSIGHT = re.compile(
    r"%\s*de candidatos|tu idoneidad|%\s*of applicants|applicant insights",
    re.IGNORECASE,
)
_CANONICAL = "https://www.linkedin.com/jobs/view/{job_id}/"


def _text(node: Tag | None) -> str:
    if node is None:
        return ""
    return " ".join(node.get_text(" ", strip=True).split())


def _card(anchor: Tag) -> Tag:
    node: Tag | None = anchor
    while node is not None:
        if node.name in {"article", "li"} or node.has_attr("data-job-id"):
            return node
        parent = node.parent
        node = parent if isinstance(parent, Tag) else None
    return anchor


def _without_insights(text: str) -> str:
    kept = [line for line in text.splitlines() if line.strip() and not _INSIGHT.search(line)]
    return "\n".join(kept).strip()


def jobs_from_search_html(html: str, *, now: datetime | None = None) -> list[JobPosting]:
    """One posting per `/jobs/view/<id>/`. Insight lines never enter the description."""
    soup = BeautifulSoup(html or "", "html.parser")
    found: list[JobPosting] = []
    seen: set[str] = set()
    for anchor in soup.find_all("a", href=True):
        if not isinstance(anchor, Tag):
            continue
        href = str(anchor.get("href") or "")
        match = _VIEW.search(href)
        if match is None:
            continue
        job_id = match.group(1)
        if job_id in seen:
            continue
        seen.add(job_id)
        card = _card(anchor)
        for aside in card.find_all("aside"):
            aside.decompose()
        title = _text(anchor) or f"Aviso {job_id}"
        company = _text(card.select_one("[data-company]")) or "empresa no indicada"
        location = _text(card.select_one("[data-location]")) or None
        posted = posted_at_from_text(_text(card.find("time")), now=now)
        description = _without_insights(_text(card.select_one("[data-description]")))
        found.append(
            JobPosting(
                id="PENDING",
                source="linkedin_jobs",
                source_job_id=job_id,
                url=_CANONICAL.format(job_id=job_id),
                title=title,
                company=company,
                location=location,
                description=description,
                raw_description=description,
                posted_at=posted,
            )
        )
    return found
