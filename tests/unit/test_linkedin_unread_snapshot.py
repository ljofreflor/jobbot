"""An empty LinkedIn snapshot is a failed read, not an empty profile."""

from __future__ import annotations

from pathlib import Path
from types import TracebackType

import pytest
import yaml

from jobbot.adapters.diff_engine import render_profile_diff, save_snapshot
from jobbot.adapters.linkedin.client import LinkedInAdapter
from jobbot.adapters.portal_status import build_profile_status
from jobbot.config import JobbotConfig, PathsConfig
from jobbot.models.candidate import Candidate
from jobbot.models.external_profile import ExternalExperience, ExternalProfile
from tests.fixtures.profile import sample_profile_dict

_HTML = """
<html><body>
  <div data-testid="experience-item">
    <span data-testid="title">Analista</span>
    <span data-testid="company">Servicio Neutro</span>
  </div>
</body></html>
"""


class _Page:
    url = "https://www.linkedin.com/in/me/"

    def goto(self, url: str, **_: object) -> None:
        self.url = url

    def content(self) -> str:
        return _HTML


class _Session:
    def __init__(self) -> None:
        self.page = _Page()

    def __enter__(self) -> _Session:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None


def _candidate() -> Candidate:
    data = sample_profile_dict()
    data["experience"] = [
        {
            "id": "role",
            "company": "Servicio Neutro",
            "title": "Analista",
            "start_date": "2020-01",
            "current": True,
            "achievements": [{"id": "a1", "text": "Cerré 12 turnos."}],
        }
    ]
    return Candidate.model_validate(data)


def test_pull_keeps_experience_when_the_headline_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(LinkedInAdapter, "_session", lambda _self: _Session())
    config = JobbotConfig(root=tmp_path, paths=PathsConfig())
    profile = LinkedInAdapter(config).pull_profile()

    assert profile.headline is None
    assert profile.experience[0].company == "Servicio Neutro"
    assert profile.experience[0].title == "Analista"


def test_an_unread_snapshot_is_not_a_diff(tmp_path: Path) -> None:
    candidate = _candidate()
    save_snapshot(ExternalProfile(source="linkedin"), tmp_path)

    report = render_profile_diff(candidate, tmp_path, "linkedin")
    education = render_profile_diff(candidate, tmp_path, "linkedin", section="education")

    assert report == "LINKEDIN snapshot was not read."
    assert education == "LINKEDIN snapshot was not read."
    assert "Servicio Neutro" not in report


def test_a_parsed_section_still_diffs(tmp_path: Path) -> None:
    candidate = _candidate()
    save_snapshot(
        ExternalProfile(
            source="linkedin",
            experience=[ExternalExperience(company="Servicio Neutro", title="Analista")],
        ),
        tmp_path,
    )

    report = render_profile_diff(candidate, tmp_path, "linkedin")

    assert "was not read" not in report
    assert "Servicio Neutro" in report


def test_status_says_unread_instead_of_a_mismatch(tmp_path: Path) -> None:
    profile_path = tmp_path / "data" / "profile.yaml"
    profile_path.parent.mkdir(parents=True)
    profile_path.write_text(yaml.safe_dump(sample_profile_dict()), encoding="utf-8")
    config = JobbotConfig(root=tmp_path, paths=PathsConfig(output=Path("output")))
    save_snapshot(ExternalProfile(source="linkedin"), config.output_dir)

    rows = {row["section"]: row for row in build_profile_status(config)["rows"]}

    assert rows["Experience"]["linkedin"] == "no leído"
    assert rows["Skills"]["linkedin"] == "no leído"
