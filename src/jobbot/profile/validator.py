"""Validate Candidate profiles beyond Pydantic field checks."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from types import UnionType
from typing import Any, Union, get_args, get_origin

from pydantic import BaseModel

from jobbot.jobs.normalization import fold_text
from jobbot.models.candidate import Candidate

UNKNOWN_KEY_MESSAGE = "clave desconocida, se ignora"


@dataclass
class ValidationIssue:
    path: str
    message: str

    def __str__(self) -> str:
        return f"{self.path}:\n{self.message}"


@dataclass
class ValidationResult:
    issues: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.issues

    def add(self, path: str, message: str) -> None:
        self.issues.append(ValidationIssue(path=path, message=message))

    def warn(self, path: str, message: str) -> None:
        self.warnings.append(ValidationIssue(path=path, message=message))


def validate_candidate(candidate: Candidate) -> ValidationResult:
    """Run cross-field and uniqueness checks."""
    result = ValidationResult()
    _check_unique_ids(candidate, result)
    _check_duplicate_achievement_text(candidate, result)
    _check_education(candidate, result)
    _check_headline_degree(candidate, result)
    return result


def _check_education(candidate: Candidate, result: ValidationResult) -> None:
    for edu in candidate.education:
        if edu.resolved_status() == "completed" and not edu.end_date:
            result.warn(f"education.{edu.id}", "completed degree has no end_date")


_CANDIDATE_HEADLINE = re.compile(r"\bdoctor c\b|\bphd candidate\b|\bcandidate\b")
_DOCTOR_HEADLINE = re.compile(r"\bdoctor\b|\bphd\b")


def _check_headline_degree(candidate: Candidate, result: ValidationResult) -> None:
    """A title the profile claims needs a degree in that state. It is not rewritten."""
    headline = fold_text(candidate.personal.headline or "")
    if not headline:
        return
    statuses = {edu.resolved_status() for edu in candidate.education}
    if _CANDIDATE_HEADLINE.search(headline):
        if "candidate" not in statuses:
            result.warn("personal.headline", "headline says candidate without a candidate degree")
        return
    if _DOCTOR_HEADLINE.search(headline) and "completed" not in statuses:
        result.warn("personal.headline", "headline says doctor without a completed degree")


def unknown_profile_keys(raw: Mapping[str, Any]) -> list[ValidationIssue]:
    """Keys in the YAML that the Candidate schema does not know (they are ignored)."""
    issues: list[ValidationIssue] = []
    _collect_unknown_keys(raw, Candidate, "", issues)
    return issues


def _collect_unknown_keys(
    value: object,
    model: type[BaseModel],
    prefix: str,
    issues: list[ValidationIssue],
) -> None:
    if not isinstance(value, Mapping):
        return
    fields = model.model_fields
    allow_extra = model.model_config.get("extra") == "allow"
    for key, child in value.items():
        name = str(key)
        path = f"{prefix}.{name}" if prefix else name
        if name not in fields:
            if not allow_extra:
                issues.append(ValidationIssue(path=path, message=UNKNOWN_KEY_MESSAGE))
            continue
        annotation = fields[name].annotation
        item_model = _list_item_model(annotation)
        if item_model is not None and isinstance(child, list):
            for index, item in enumerate(child):
                if not isinstance(item, Mapping):
                    continue
                item_id = item.get("id")
                item_prefix = f"{path}.{item_id}" if item_id else f"{path}.{index}"
                _collect_unknown_keys(item, item_model, item_prefix, issues)
            continue
        nested = _nested_model(annotation)
        if nested is not None:
            _collect_unknown_keys(child, nested, path, issues)


def _nested_model(annotation: object) -> type[BaseModel] | None:
    origin = get_origin(annotation)
    if origin in {Union, UnionType}:
        candidates = [arg for arg in get_args(annotation) if arg is not type(None)]
        return _nested_model(candidates[0]) if len(candidates) == 1 else None
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return annotation
    return None


def _list_item_model(annotation: object) -> type[BaseModel] | None:
    origin = get_origin(annotation)
    if origin is list:
        args = get_args(annotation)
        return _nested_model(args[0]) if args else None
    return _nested_model(annotation)


def _check_unique_ids(candidate: Candidate, result: ValidationResult) -> None:
    exp_ids = [e.id for e in candidate.experience]
    _assert_unique(exp_ids, "experience", result)

    edu_ids = [e.id for e in candidate.education]
    _assert_unique(edu_ids, "education", result)

    pub_ids = [p.id for p in candidate.publications]
    _assert_unique(pub_ids, "publications", result)

    project_ids = [p.id for p in candidate.projects]
    _assert_unique(project_ids, "projects", result)

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
