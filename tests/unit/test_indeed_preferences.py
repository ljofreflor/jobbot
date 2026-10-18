"""Indeed Preferencias: trim to 10, needs_human salary, refuse save, missing tab."""

from __future__ import annotations

from pathlib import Path
from types import TracebackType

import pytest
import yaml

from jobbot.adapters.indeed.client import IndeedAdapter
from jobbot.cli import run_cli
from jobbot.jobs.eligibility import ApplicationAnswers
from jobbot.profile.loader import load_profile

FIXTURES = Path("tests/fixtures/indeed")


def _workspace(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    titles: int = 12,
    job_types: list[str] | None = None,
) -> None:
    data = tmp_path / "data"
    data.mkdir()
    (tmp_path / "output").mkdir()
    example = project_root / "data" / "profile.example.yaml"
    raw = yaml.safe_load(example.read_text(encoding="utf-8"))
    raw["search_queries"] = [f"Cargo {index:02d}" for index in range(1, titles + 1)]
    (data / "profile.yaml").write_text(
        yaml.safe_dump(raw, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    if job_types:
        (data / "application_answers.yaml").write_text(
            yaml.safe_dump({"job_types": job_types}, allow_unicode=True),
            encoding="utf-8",
        )
    (tmp_path / ".jobbot.toml").write_text(
        f'[paths]\ntemplates = "{project_root / "templates"}"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)


class _Page:
    def __init__(self, html: str) -> None:
        self.html = html
        self.url = "https://profile.indeed.com/resume"
        self.clicks: list[str] = []

    def goto(self, url: str, **_: object) -> None:
        self.url = url

    def wait_for_selector(self, selector: str, timeout: float | None = None) -> None:
        del selector, timeout

    def content(self) -> str:
        return self.html

    def inner_text(self, selector: str) -> str:
        del selector
        return ""

    def click(self, selector: str, **_: object) -> None:
        self.clicks.append(selector)


class _Session:
    def __init__(self, page: _Page) -> None:
        self.page = page

    def __enter__(self) -> _Session:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None


def test_preferences_plan_trims_titles_and_keeps_going_without_salary(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    html = (project_root / FIXTURES / "preferences.html").read_text(encoding="utf-8")
    assert "Preferencias" in html
    assert "Cargos deseados" in html
    _workspace(tmp_path, project_root, monkeypatch, job_types=["full_time"])

    def refuse_session(_self: IndeedAdapter) -> _Session:
        raise AssertionError("el plan seco no abre sesión")

    monkeypatch.setattr(IndeedAdapter, "_session", refuse_session)
    code = run_cli(["indeed", "sync", "--section", "preferences"], standalone_mode=False)
    captured = capsys.readouterr()
    assert code == 0
    cargo = [line for line in captured.out.splitlines() if line.startswith("cargos  ADD")]
    assert len(cargo) == 10
    assert "recorte: 2 cargos quedan fuera del máximo de 10" in captured.out
    assert "sueldo  needs_human" in captured.out
    assert "tipos  ADD  full_time" in captured.out
    assert not (tmp_path / "output" / "indeed" / "cv_receipt.yaml").exists()


def test_apply_no_does_not_click_save(
    tmp_path: Path, project_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    page = _Page("<html></html>")
    monkeypatch.setattr(IndeedAdapter, "_session", lambda _self: _Session(page))
    monkeypatch.setattr("jobbot.cli.typer.confirm", lambda *_args, **_kwargs: False)
    code = run_cli(
        ["indeed", "sync", "--section", "preferences", "--apply"],
        standalone_mode=False,
    )
    assert code == 130
    assert page.clicks == []


def test_pull_without_preferences_tab_exits_ui_changed(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch, titles=0)
    html = (project_root / FIXTURES / "no_preferences.html").read_text(encoding="utf-8")
    page = _Page(html)
    monkeypatch.setattr(IndeedAdapter, "_session", lambda _self: _Session(page))
    code = run_cli(["indeed", "pull"], standalone_mode=False)
    captured = capsys.readouterr()
    assert code == 5
    assert "Preferencias" in captured.out


def test_planner_marks_salary_needs_human_and_keeps_other_rows(
    tmp_path: Path, project_root: Path
) -> None:
    from jobbot.adapters.indeed.preferences import plan_preferences

    raw = yaml.safe_load(
        (project_root / "data" / "profile.example.yaml").read_text(encoding="utf-8")
    )
    raw["search_queries"] = ["Uno"]
    profile = tmp_path / "profile.yaml"
    profile.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    plan = plan_preferences(
        load_profile(profile),
        ApplicationAnswers.model_validate({"job_types": ["contract"]}),
    )
    assert "sueldo  needs_human" in plan.lines
    assert "tipos  ADD  contract" in plan.lines
