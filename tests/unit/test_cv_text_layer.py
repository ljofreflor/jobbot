"""The CV text layer keeps contact as characters and does not stuff job terms."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from jobbot.cv.build import BuildTarget, build_cv
from jobbot.cv.text_layer import TextLayerIssue, check_text_layer, issues_in_text
from jobbot.exit_codes import SUCCESS, VALIDATION_FAILURE
from jobbot.matching.analyzer import RuleBasedJobAnalyzer
from jobbot.models.candidate import Candidate
from jobbot.models.job import JobPosting
from tests.fixtures.cv_pdf import SubsetFont, build_pdf, content_stream, write_subset_font_cv
from tests.fixtures.profile import sample_profile_dict

EMAIL = "persona@example.org"
PHONE = "+56911111111"


def _candidate() -> Candidate:
    raw = sample_profile_dict()
    raw["personal"]["email"] = EMAIL
    raw["personal"]["phone"] = PHONE
    raw["personal"]["linkedin"] = "https://www.linkedin.com/in/persona-demo"
    return Candidate.model_validate(raw)


def test_icon_and_bullet_glyphs_are_reported(tmp_path: Path) -> None:
    font = SubsetFont(
        name="F1",
        base_font="AAAAAA+Icons",
        widths={
            code: 400
            for code in (ord("Y"), ord("P"), ord("f"), ord(" "), *map(ord, "unlogro"))
        },
        to_unicode={
            ord("Y"): "Ȳ",
            ord("P"): PHONE,
            ord("f"): "f",
            ord(" "): " ",
            **{ord(ch): ch for ch in "unlogro"},
        },
    )
    path = write_subset_font_cv(
        tmp_path / "icons.pdf",
        [font],
        [("F1", "YP"), ("F1", "f un logro")],
    )
    kinds = {issue.kind for issue in check_text_layer(path, _candidate())}
    assert "icon_glyph" in kinds
    assert "bullet_glyph" in kinds


def test_contact_is_literal_text(tmp_path: Path) -> None:
    page = "\n".join(
        [
            "Persona Demo",
            f" {EMAIL}",
            f" {PHONE}",
            " linkedin.com/in/persona-demo",
            "- escribe informes",
        ]
    )
    path = tmp_path / "clean.pdf"
    build_pdf([content_stream(page)], path)
    issues = check_text_layer(path, _candidate())
    assert issues == []
    text = path.read_bytes()
    assert EMAIL.encode() in text or EMAIL in page


def test_unknown_term_is_a_gap_and_stays_off_the_cv(tmp_path: Path, project_root: Path) -> None:
    candidate = _candidate()
    job = JobPosting(
        id="J0202",
        source="manual",
        title="Analyst",
        company="Estudio Neutro",
        description="Una descripcion de un aviso. " * 20,
        skills=["QuimeraX"],
    )
    outputs = build_cv(
        candidate,
        project_root / "templates",
        tmp_path / "output",
        target=BuildTarget.ATS,
        job=job,
        match=RuleBasedJobAnalyzer().analyze(candidate, job),
    )
    ats = next(path for path in outputs if path.name == "cv_ats.txt").read_text(encoding="utf-8")
    payload = json.loads(
        (tmp_path / "output" / "jobs" / "J0202" / "selection.json").read_text(encoding="utf-8")
    )
    assert "QuimeraX" not in ats
    assert "QuimeraX" in payload["gaps"]
    assert issues_in_text(ats, candidate, job=job) == []


def test_strict_build_exits_when_the_layer_has_a_finding(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "profile.yaml").write_text(
        (project_root / "data" / "profile.example.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (tmp_path / ".jobbot.toml").write_text(
        f'[paths]\ntemplates = "{project_root / "templates"}"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    import jobbot.cv.text_layer as layer
    from jobbot.cli import run_cli

    monkeypatch.setattr(
        layer,
        "issues_for_outputs",
        lambda *_args, **_kwargs: [TextLayerIssue("icon_glyph", "icon glyph before contact")],
    )
    code = run_cli(["cv", "build", "--target", "ats", "--strict"], standalone_mode=False)
    assert code == VALIDATION_FAILURE
    assert "icon_glyph" in capsys.readouterr().err


def test_clean_ats_build_stays_success(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "profile.yaml").write_text(
        (project_root / "data" / "profile.example.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (tmp_path / ".jobbot.toml").write_text(
        f'[paths]\ntemplates = "{project_root / "templates"}"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    from jobbot.cli import run_cli

    assert run_cli(["cv", "build", "--target", "ats", "--strict"], standalone_mode=False) == SUCCESS
