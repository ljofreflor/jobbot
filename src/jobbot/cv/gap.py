"""Which posting terms the profile already evidences, and which stay questions.

Missing terms are never written into ``profile.yaml`` or the CV. An unknown
term stays a hard skill. A short exact list marks interpersonal phrases as
soft; they are reported apart and never promoted.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from jobbot.jobs.normalization import fold_text, normalize_skill
from jobbot.jobs.parsing import extract_skills_from_text
from jobbot.models.candidate import Candidate
from jobbot.models.job import JobPosting

# Exact folds only. Anything else stays hard, so a new craft is not dropped.
_SOFT = frozenset(
    {
        "comunicacion",
        "communication",
        "trabajo en equipo",
        "teamwork",
        "liderazgo",
        "leadership",
    }
)


class GapStatus(StrEnum):
    MATCHED = "matched"
    GAP = "gap"


@dataclass(frozen=True)
class GapTerm:
    """One posting term, where it was written, and the profile fact that covers it."""

    term: str
    kind: str
    status: GapStatus
    span: tuple[int, int]
    evidence: str

    def as_dict(self) -> dict[str, object]:
        return {
            "term": self.term,
            "kind": self.kind,
            "status": self.status.value,
            "span": [self.span[0], self.span[1]],
            "evidence": self.evidence,
        }


@dataclass(frozen=True)
class GapReport:
    """Hard terms drive the counts. Soft terms are listed and not promoted."""

    job_id: str
    terms: tuple[GapTerm, ...]

    @property
    def matched(self) -> int:
        return sum(
            1
            for term in self.terms
            if term.kind == "hard" and term.status is GapStatus.MATCHED
        )

    @property
    def missing(self) -> int:
        return sum(
            1 for term in self.terms if term.kind == "hard" and term.status is GapStatus.GAP
        )

    def as_dict(self) -> dict[str, object]:
        hard = [term.as_dict() for term in self.terms if term.kind == "hard"]
        soft = [term.as_dict() for term in self.terms if term.kind == "soft"]
        return {
            "job_id": self.job_id,
            "matched": self.matched,
            "missing": self.missing,
            "hard": hard,
            "soft": soft,
        }

    def lines(self) -> tuple[str, ...]:
        rows = [f"matched {self.matched}  missing {self.missing}"]
        for term in self.terms:
            mark = "MATCH" if term.status is GapStatus.MATCHED else "GAP"
            where = f"  {term.evidence}" if term.evidence else ""
            rows.append(f"{term.kind}  {mark}  {term.term}{where}")
        return tuple(rows)


def gap_report(candidate: Candidate, job: JobPosting) -> GapReport:
    """Terms the posting names, each matched or left as a gap."""
    text = _posting_text(job)
    terms = []
    for skill in extract_skills_from_text(text):
        evidence = _evidence(skill, candidate)
        terms.append(
            GapTerm(
                term=skill,
                kind="soft" if fold_text(skill) in _SOFT else "hard",
                status=GapStatus.MATCHED if evidence else GapStatus.GAP,
                span=_span(text, skill),
                evidence=evidence,
            )
        )
    return GapReport(job_id=job.id, terms=tuple(terms))


def write_gap_report(report: GapReport, output_dir: Path) -> Path:
    """Cache the report. Does not touch the profile or the job row."""
    path = output_dir / "jobs" / report.job_id / "gap.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.as_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _posting_text(job: JobPosting) -> str:
    parts = [job.description, job.raw_description, *job.requirements]
    return "\n".join(part for part in parts if part)


def _span(text: str, term: str) -> tuple[int, int]:
    start = text.casefold().find(term.casefold())
    if start < 0:
        return (0, 0)
    return (start, start + len(term))


def _evidence(term: str, candidate: Candidate) -> str:
    token = normalize_skill(term)
    for skill in candidate.skills.all_skills():
        if normalize_skill(skill) == token:
            return f"skill:{skill}"
    for specialty in candidate.specialties:
        if normalize_skill(specialty) == token or fold_text(term) in fold_text(specialty):
            return f"specialty:{specialty}"
    folded = fold_text(term)
    for exp in candidate.experience:
        if folded and folded in fold_text(exp.title):
            return f"title:{exp.id}"
        for ach in exp.achievements:
            if folded and folded in fold_text(ach.text):
                return f"achievement:{ach.id}"
    if folded and folded in fold_text(candidate.summary or ""):
        return "summary"
    return ""
