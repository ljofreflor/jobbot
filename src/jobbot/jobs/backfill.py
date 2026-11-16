"""Fill in facts JobBot learned to read after some jobs were already stored."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from jobbot.jobs.repository import JobRepository
    from jobbot.models.job import JobPosting


def backfill_posted_at(repo: JobRepository) -> int:
    """
    Date already-stored posts from the activity id in their URL.

    Deterministic and offline: nothing is fetched, and rows that already have a
    date or carry no activity id are left untouched. Returns rows updated.
    """
    from jobbot.adapters.linkedin.sweep import posted_at_from_url

    updated = 0
    for job in repo.list_all():
        if job.posted_at is not None or not job.url:
            continue
        posted = posted_at_from_url(job.url)
        if posted is None:
            continue
        job.posted_at = posted
        repo.save(job)
        updated += 1
    return updated


def reparse_stored(repo: JobRepository, job_id: str) -> JobPosting:
    """Read the stored text again and keep the id. Nothing is fetched."""
    from jobbot.jobs.parsing import parse_job_text

    job = repo.get(job_id)
    if job is None:
        raise KeyError(job_id)
    text = (job.raw_description or job.description or "").strip()
    if not text:
        return job
    parsed = parse_job_text(text, job_id=job.id, source=job.source, url=job.url)
    job.title = parsed.title
    if parsed.company != "Unknown":
        job.company = parsed.company
    job.requirements = list(parsed.requirements)
    job.skills = list(parsed.skills)
    if parsed.location:
        job.location = parsed.location
    repo.save(job)
    return job
