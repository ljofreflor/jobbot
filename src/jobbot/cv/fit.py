"""Compare base vs job-adapted ATS text against a job description."""

from __future__ import annotations

from pathlib import Path

from jobbot.cv.ats import build_ats_text
from jobbot.cv.selection import select_for_base_cv, select_for_job
from jobbot.matching.similarity import (
    AdaptationFit,
    TextEmbedder,
    compare_adaptation_fit,
)
from jobbot.models.candidate import Candidate
from jobbot.models.job import JobPosting
from jobbot.models.match import JobMatch


def compare_base_vs_adapted_cv(
    candidate: Candidate,
    job: JobPosting,
    templates_dir: Path,
    *,
    match: JobMatch | None = None,
    embedder: TextEmbedder | None = None,
    base_ats: str | None = None,
    adapted_ats: str | None = None,
) -> AdaptationFit:
    """Build (or reuse) ATS texts and score each against the same JD.

    Expectation: the job-adapted CV scores closer / higher than the base CV.
    """
    if base_ats is None:
        base_ats = build_ats_text(candidate, templates_dir, select_for_base_cv(candidate))
    if adapted_ats is None:
        adapted_ats = build_ats_text(
            candidate, templates_dir, select_for_job(candidate, job, match)
        )
    return compare_adaptation_fit(base_ats, adapted_ats, job, embedder=embedder)


def load_ats_pair(
    output_dir: Path,
    job_id: str,
) -> tuple[str | None, str | None]:
    """Read written ``cv_ats.txt`` files when present (base + jobs/<id>)."""
    base_path = output_dir / "base" / "cv_ats.txt"
    adapted_path = output_dir / "jobs" / job_id / "cv_ats.txt"
    base = base_path.read_text(encoding="utf-8") if base_path.is_file() else None
    adapted = adapted_path.read_text(encoding="utf-8") if adapted_path.is_file() else None
    return base, adapted
