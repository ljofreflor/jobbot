"""Get on Board skills, seniority and English stay inside what the profile states (#287)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from jobbot.adapters.getonboard.profile_edit import ProfileEditError
from jobbot.adapters.getonboard.profile_fields import (
    OBSERVED_ENGLISH,
    OBSERVED_SENIORITY,
    SKILLS_SELECTOR,
    experience_years,
    options_for,
    plan_skills,
    project_english,
    project_seniority,
    set_skills_select,
)
from jobbot.exit_codes import SUCCESS
from jobbot.models.candidate import Candidate

FIXTURE = Path(__file__).parents[1] / "fixtures" / "getonboard" / "webpros_edit_skills.html"


def test_twelve_skills_plan_keeps_ten_and_marks_the_ones_without_a_level() -> None:
    names = [f"Habilidad {index}" for index in range(1, 13)]
    plan = plan_skills(names, {names[0]: "proficient"})

    assert len(plan.rows) == 10
    assert plan.rows[0].status == "planned"
    assert all(row.status == "needs_human" for row in plan.rows[1:])
    assert len(plan.trimmed) == 2
    assert "recorte" in plan.note


def test_hidden_skills_select_is_set_with_value_and_change() -> None:
    class Hidden:
        def __init__(self) -> None:
            self.visible = False
            self.calls: list[tuple[str, object]] = []

        def evaluate(self, expression: str, arg: object = None) -> None:
            assert self.visible is False
            self.calls.append((expression, arg))

    class Page:
        def __init__(self) -> None:
            self.element = Hidden()

        def query_selector(self, selector: str) -> Hidden | None:
            return self.element if selector == SKILLS_SELECTOR else None

    page = Page()
    set_skills_select(page, "10")  # type: ignore[arg-type]

    expression, value = page.element.calls[0]
    assert "node.value = value" in expression
    assert "change" in expression
    assert value == "10"


def test_missing_skills_select_names_the_control() -> None:
    class Page:
        def query_selector(self, _selector: str) -> None:
            return None

    with pytest.raises(ProfileEditError, match="skills"):
        set_skills_select(Page(), "10")  # type: ignore[arg-type]


def test_english_b2_uses_the_fixture_option_and_an_unknown_level_does_not() -> None:
    html = FIXTURE.read_text(encoding="utf-8")
    options = options_for(html, "webpro[english_level]")

    assert options == list(OBSERVED_ENGLISH)
    assert project_english("B2", options) == "4"
    assert project_english("A1", options) is None


def test_seniority_follows_the_fixture_bands() -> None:
    html = FIXTURE.read_text(encoding="utf-8")
    options = options_for(html, "webpro[seniority_ids][]")
    candidate = Candidate.model_validate(
        {
            "personal": {"name": "Ana Ejemplo", "headline": "Profesional"},
            "experience": [
                {
                    "id": "e1",
                    "company": "Organismo Ejemplo",
                    "title": "Profesional",
                    "start_date": "2019-01",
                    "end_date": "2026-01",
                }
            ],
        }
    )

    assert options == list(OBSERVED_SENIORITY)
    assert project_seniority(experience_years(candidate.experience), options) == "3"


def test_cli_sync_section_skills_trims_and_marks_missing_levels(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    names = [f"Habilidad {index}" for index in range(1, 13)]
    data = tmp_path / "data"
    data.mkdir()
    (tmp_path / "output").mkdir()
    profile = {
        "personal": {"name": "Ana Ejemplo", "headline": "Profesional"},
        "skills": {"oficio": names, "levels": {names[0]: "proficient"}},
    }
    (data / "profile.yaml").write_text(
        yaml.safe_dump(profile, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    from jobbot.cli import run_cli

    code = run_cli(["getonboard", "sync", "--section", "skills"], standalone_mode=False)
    out = capsys.readouterr().out
    skill_lines = [line for line in out.splitlines() if line.startswith("skill ")]

    assert code == SUCCESS
    assert len(skill_lines) == 10
    assert any("needs_human" in line for line in skill_lines)
    assert "recorte" in out
