"""Structural CV checks. A failure asks a question; it never adds a fact.

The report is deterministic. A suggestion that names a skill the profile does
not already contain is dropped.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from jobbot.cv.gap import GapStatus, gap_report
from jobbot.jobs.normalization import fold_text, normalize_skill
from jobbot.jobs.parsing import extract_skills_from_text
from jobbot.models.candidate import Candidate
from jobbot.models.job import JobPosting

_DIGIT = re.compile(r"\d")


class CheckStatus(StrEnum):
    PASS = "pass"
    FAIL = "fail"


@dataclass(frozen=True)
class Check:
    """One checklist row. ``id`` is stable for tests and later advise."""

    id: str
    status: CheckStatus
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {"id": self.id, "status": self.status.value, "detail": self.detail}


@dataclass(frozen=True)
class CvCheckReport:
    checks: tuple[Check, ...]

    def as_dict(self) -> dict[str, object]:
        return {"checks": [check.as_dict() for check in self.checks]}

    def lines(self) -> tuple[str, ...]:
        return tuple(f"{check.status.value}  {check.id}  {check.detail}" for check in self.checks)


def check_cv(candidate: Candidate, job: JobPosting | None = None) -> CvCheckReport:
    """Checklist for the profile, plus missing posting terms when a job is given."""
    checks = [_quantified(candidate)]
    if job is not None:
        checks.append(_hard_skills(candidate, job))
    return CvCheckReport(checks=tuple(checks))


def accepted_suggestion(candidate: Candidate, text: str) -> str | None:
    """Keep a presentation note only when it adds no skill the profile lacks."""
    known = _known_tokens(candidate)
    whole = fold_text(text).strip(" .")
    for skill in extract_skills_from_text(text):
        if fold_text(skill) == whole:
            continue
        if normalize_skill(skill) not in known:
            return None
    return text


def write_cv_check(report: CvCheckReport, output_dir: Path) -> Path:
    """Cache the checklist. Does not touch the profile."""
    path = output_dir / "cv" / "check.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.as_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _quantified(candidate: Candidate) -> Check:
    bullets = [ach.text for exp in candidate.experience for ach in exp.achievements]
    if any(_DIGIT.search(text) for text in bullets):
        return Check("quantified_bullets", CheckStatus.PASS, "a bullet already contains a number")
    return Check("quantified_bullets", CheckStatus.FAIL, "no bullet contains a number")


def _hard_skills(candidate: Candidate, job: JobPosting) -> Check:
    missing = [
        term.term
        for term in gap_report(candidate, job).terms
        if term.kind == "hard" and term.status is GapStatus.GAP
    ]
    if not missing:
        return Check("hard_skills_missing", CheckStatus.PASS, "posting terms are covered")
    return Check("hard_skills_missing", CheckStatus.FAIL, ", ".join(missing))


def _known_tokens(candidate: Candidate) -> set[str]:
    tokens = {normalize_skill(skill) for skill in candidate.skills.all_skills()}
    tokens.update(normalize_skill(name) for name in candidate.specialties)
    return {token for token in tokens if token}
