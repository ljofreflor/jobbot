"""Validate Candidate profiles beyond Pydantic field checks."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field

from jobbot.models.candidate import Candidate


@dataclass
class ValidationIssue:
    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}:\n{self.message}"


@dataclass
class ValidationResult:
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues

    def add(self, path: str, message: str) -> None:
        self.issues.append(ValidationIssue(path=path, message=message))


def validate_candidate(candidate: Candidate) -> ValidationResult:
    """Run cross-field and uniqueness checks."""
    result = ValidationResult()
    _check_unique_ids(candidate, result)
    _check_duplicate_achievement_text(candidate, result)
    return result


def _check_unique_ids(candidate: Candidate, result: ValidationResult) -> None:
    exp_ids = [e.id for e in candidate.experience]
    _assert_unique(exp_ids, "experience", result)

    edu_ids = [e.id for e in candidate.education]
    _assert_unique(edu_ids, "education", result)

    pub_ids = [p.id for p in candidate.publications]
    _assert_unique(pub_ids, "publications", result)

    ach_ids = [a.id for exp in candidate.experience for a in exp.achievements]
    _assert_unique(ach_ids, "achievements", result)


def _assert_unique(ids: list[str], section: str, result: ValidationResult) -> None:
    counts = Counter(ids)
    for item_id, count in counts.items():
        if count > 1:
            result.add(f"{section}.{item_id}", f"duplicate id (appears {count} times)")


def _check_duplicate_achievement_text(candidate: Candidate, result: ValidationResult) -> None:
    texts: dict[str, str] = {}
    for exp in candidate.experience:
        for ach in exp.achievements:
            key = " ".join(ach.text.split()).casefold()
            if key in texts:
                result.add(
                    ach.id,
                    f"duplicate achievement text (same as {texts[key]})",
                )
            else:
                texts[key] = ach.id
