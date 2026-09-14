"""Tests for profile loading and validation."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from jobbot.models.candidate import Candidate
from jobbot.profile.loader import ProfileLoadError, load_profile
from jobbot.profile.validator import validate_candidate
from tests.fixtures.profile import sample_profile_dict


def test_load_example_profile(project_root: Path) -> None:
    path = project_root / "data" / "profile.example.yaml"
    candidate = load_profile(path)
    assert candidate.personal.name == "Ana Ejemplo"
    assert len(candidate.experience) >= 1
    assert candidate.achievement_count() >= 1


def test_validate_ok() -> None:
    candidate = Candidate.model_validate(sample_profile_dict())
    result = validate_candidate(candidate)
    assert result.ok


def test_duplicate_experience_id() -> None:
    data = sample_profile_dict()
    data["experience"].append({**data["experience"][0], "id": "meli-ds"})
    candidate = Candidate.model_validate(data)
    result = validate_candidate(candidate)
    assert not result.ok
    assert any("duplicate id" in i.message for i in result.issues)


def test_end_before_start_rejected() -> None:
    data = sample_profile_dict()
    data["experience"][0]["start_date"] = "2024-01"
    data["experience"][0]["end_date"] = "2020-01"
    with pytest.raises(ValidationError):
        Candidate.model_validate(data)


def test_invalid_email_rejected() -> None:
    data = sample_profile_dict()
    data["personal"]["email"] = "not-an-email"
    with pytest.raises(ValidationError):
        Candidate.model_validate(data)


def test_duplicate_achievement_text() -> None:
    data = sample_profile_dict()
    data["experience"][0]["achievements"].append(
        {
            "id": "other-id",
            "text": "Share of Wallet for 6M sellers.",
            "tags": [],
            "metrics": {},
        }
    )
    candidate = Candidate.model_validate(data)
    result = validate_candidate(candidate)
    assert not result.ok
    assert any("duplicate achievement text" in i.message for i in result.issues)


def test_missing_profile_file(tmp_path: Path) -> None:
    with pytest.raises(ProfileLoadError, match="not found"):
        load_profile(tmp_path / "missing.yaml")


def test_load_from_tmp(tmp_path: Path) -> None:
    path = tmp_path / "profile.yaml"
    path.write_text(yaml.safe_dump(sample_profile_dict()), encoding="utf-8")
    candidate = load_profile(path)
    assert candidate.personal.email == "ana@example.com"
