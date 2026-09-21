"""Ingest a hard job URL: know the portal, fetch the JD, store, match, prepare."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from jobbot.adapters.getonboard.jobs import job_from_hard_link, remember_portal
from jobbot.applications.manager import (
    ApplicationRepository,
    prepare_application_package,
)
from jobbot.config import JobbotConfig
from jobbot.cv.build import BuildTarget, build_cv, should_rebuild_job_cv
from jobbot.jobs.repository import JobRepository, write_job_json
from jobbot.matching.analyzer import RuleBasedJobAnalyzer
from jobbot.models.application import ApplicationStatus
from jobbot.models.candidate import Candidate
from jobbot.models.job import JobPosting
from jobbot.models.match import JobMatch
from jobbot.portals.detect import AtsKind
from jobbot.portals.knowledge import PortalKnowledge, lookup_portal


class UnknownPortalError(ValueError):
    """The URL's host is not in local portals, the seed, or built-in ATS rules."""


class UnsupportedPortalFetchError(ValueError):
    """Portal is known but JobBot cannot fetch a JD from that host yet."""


@dataclass(frozen=True)
class GetFromUrlResult:
    job: JobPosting
    portal: PortalKnowledge
    match: JobMatch | None
    package_dir: Path | None
    job_json: Path


def ingest_hard_link(
    config: JobbotConfig,
    session: Session,
    url: str,
    *,
    candidate: Candidate,
    html: str | None = None,
    build: bool = True,
    prepare: bool = True,
    on_chunk: Callable[[int, int | None], None] | None = None,
) -> GetFromUrlResult:
    """Know the portal → fetch → store → match → CV + application package.

    Does not open a browser or submit. Callers use ``application apply --apply``
    (or the CLI ``get --apply``) for HITL send.
    """
    portal = lookup_portal(config, url)
    if not portal.known:
        domain = portal.domain or "(no host)"
        msg = (
            f"Unknown employment domain: {domain}. "
            "Add it with `jobbot portals add` or `jobbot companies learn`, "
            "or use a known ATS hard link."
        )
        raise UnknownPortalError(msg)

    job = _fetch_job(portal, html=html, on_chunk=on_chunk)
    remember_portal(
        config,
        url=portal.url,
        ats_kind=portal.ats_kind,
        notes=f"hard link ({portal.source.value})",
    )

    repo = JobRepository(session)
    stored = repo.upsert_external(job)
    job_json = write_job_json(stored, config.output_dir)

    match: JobMatch | None = None
    package_dir: Path | None = None
    if build or prepare:
        match = RuleBasedJobAnalyzer().analyze(candidate, stored)
        repo.update_match_score(stored.id, match.score)
        stored.match_score = match.score
        if build:
            _build_adapted_cv(config, candidate, stored, match)
        if prepare:
            job_dir = config.output_dir / "jobs" / stored.id
            package_dir = prepare_application_package(
                stored, config.output_dir, job_dir=job_dir, candidate=candidate
            )
            ApplicationRepository(session).upsert_for_job(
                stored.id,
                status=ApplicationStatus.PREPARED,
                package_dir=str(package_dir),
            )

    return GetFromUrlResult(
        job=stored,
        portal=portal,
        match=match,
        package_dir=package_dir,
        job_json=job_json,
    )


def _fetch_job(
    portal: PortalKnowledge,
    *,
    html: str | None,
    on_chunk: Callable[[int, int | None], None] | None = None,
) -> JobPosting:
    if portal.ats_kind == AtsKind.GETONBOARD:
        return job_from_hard_link(portal.url, html=html, on_chunk=on_chunk)
    msg = (
        f"No hard-link fetcher for {portal.ats_kind.value} yet "
        f"({portal.domain}). Use `jobbot jobs add --file` or a Get on Board URL."
    )
    raise UnsupportedPortalFetchError(msg)


def _build_adapted_cv(
    config: JobbotConfig,
    candidate: Candidate,
    job: JobPosting,
    match: JobMatch,
) -> None:
    job_dir = config.output_dir / "jobs" / job.id
    if not should_rebuild_job_cv(job_dir, config.profile_path):
        return
    try:
        build_cv(
            candidate,
            config.templates_dir,
            config.output_dir,
            target=BuildTarget.CV,
            job=job,
            match=match,
        )
    except RuntimeError:
        build_cv(
            candidate,
            config.templates_dir,
            config.output_dir,
            target=BuildTarget.ATS,
            job=job,
            match=match,
        )
