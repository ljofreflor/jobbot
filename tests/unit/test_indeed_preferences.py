"""Indeed Preferencias: trim to 10, needs_human salary, refuse save, missing tab."""

from __future__ import annotations

import re
from pathlib import Path
from types import TracebackType

import pytest
import yaml

from jobbot.adapters.indeed.client import IndeedAdapter
from jobbot.adapters.indeed.preferences import (
    AVAILABILITY_LABEL,
    JOB_TYPES_LABEL,
    SAVE_SELECTOR,
    TITLES_LABEL,
)
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
    answers: dict[str, object] | None = None,
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
    stated: dict[str, object] = dict(answers or {})
    if job_types:
        stated["job_types"] = job_types
    if stated:
        (data / "application_answers.yaml").write_text(
            yaml.safe_dump(stated, allow_unicode=True),
            encoding="utf-8",
        )
    (tmp_path / ".jobbot.toml").write_text(
        f'[paths]\ntemplates = "{project_root / "templates"}"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)


class _Locator:
    def __init__(self, page: _Page, name: str, present: bool) -> None:
        self._page = page
        self._name = name
        self._present = present

    def count(self) -> int:
        return 1 if self._present else 0

    @property
    def first(self) -> _Locator:
        return self

    def fill(self, value: str) -> None:
        self._page.fills.append((self._name, value))

    def click(self, **_: object) -> None:
        self._page.clicks.append(self._name)


class _Keyboard:
    def __init__(self, page: _Page) -> None:
        self._page = page

    def press(self, key: str) -> None:
        self._page.keys.append(key)


class _Page:
    def __init__(self, html: str) -> None:
        self.html = html
        self.url = "https://profile.indeed.com/resume"
        self.clicks: list[str] = []
        self.gotos: list[str] = []
        self.fills: list[tuple[str, str]] = []
        self.keys: list[str] = []
        self.keyboard = _Keyboard(self)
        self.labels = {
            text.strip()
            for text in re.findall(r"<label[^>]*>(.*?)</label>", html, flags=re.DOTALL)
        }

    def goto(self, url: str, **_: object) -> None:
        self.url = url
        self.gotos.append(url)

    def wait_for_selector(self, selector: str, timeout: float | None = None) -> None:
        del timeout
        if selector == SAVE_SELECTOR and 'name="save"' not in self.html:
            msg = f"no hay {selector}"
            raise RuntimeError(msg)

    def content(self) -> str:
        return self.html

    def inner_text(self, selector: str) -> str:
        del selector
        return ""

    def click(self, selector: str, **_: object) -> None:
        self.clicks.append(selector)

    def get_by_label(self, label: str) -> _Locator:
        return _Locator(self, label, label in self.labels)

    def get_by_role(self, role: str, *, name: str = "") -> _Locator:
        del role
        return _Locator(self, name, f">{name}<" in self.html)


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


def test_apply_opens_preferencias_and_types_the_plan(
    tmp_path: Path, project_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _workspace(
        tmp_path,
        project_root,
        monkeypatch,
        titles=2,
        job_types=["full_time"],
        answers={"availability": {"from_date": "2026-11-03"}},
    )
    html = (project_root / FIXTURES / "preferences.html").read_text(encoding="utf-8")
    page = _Page(html)
    monkeypatch.setattr(IndeedAdapter, "_session", lambda _self: _Session(page))
    code = run_cli(
        ["indeed", "sync", "--section", "preferences", "--apply", "--yes"],
        standalone_mode=False,
    )
    assert code == 0
    assert page.gotos == ["https://profile.indeed.com/resume"]
    assert (TITLES_LABEL, "Cargo 01") in page.fills
    assert (TITLES_LABEL, "Cargo 02") in page.fills
    assert (JOB_TYPES_LABEL, "full_time") in page.fills
    assert (AVAILABILITY_LABEL, "2026-11-03") in page.fills
    assert page.clicks == ["Preferencias", SAVE_SELECTOR]


def test_apply_does_not_save_a_page_without_preferencias(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch, titles=1)
    html = (project_root / FIXTURES / "no_preferences.html").read_text(encoding="utf-8")
    page = _Page(html)
    monkeypatch.setattr(IndeedAdapter, "_session", lambda _self: _Session(page))
    code = run_cli(
        ["indeed", "sync", "--section", "preferences", "--apply", "--yes"],
        standalone_mode=False,
    )
    captured = capsys.readouterr()
    assert code == 5
    assert "Preferencias" in captured.out
    assert page.clicks == []
    assert page.fills == []


def test_net_salary_is_not_planned_onto_indeed_pay(
    tmp_path: Path, project_root: Path
) -> None:
    from jobbot.adapters.indeed.preferences import plan_preferences

    raw = yaml.safe_load(
        (project_root / "data" / "profile.example.yaml").read_text(encoding="utf-8")
    )
    raw["search_queries"] = ["Uno"]
    profile = tmp_path / "profile.yaml"
    profile.write_text(yaml.safe_dump(raw, allow_unicode=True), encoding="utf-8")
    candidate = load_profile(profile)
    liquido = {"amount": 2000000, "currency": "CLP", "period": "month", "basis": "net"}
    net = plan_preferences(
        candidate, ApplicationAnswers.model_validate({"salary": liquido})
    )
    assert net.pay is None
    assert not [line for line in net.lines if line.startswith("sueldo  ADD")]
    assert any(line.startswith("sueldo  needs_human") for line in net.lines)
    gross = plan_preferences(
        candidate,
        ApplicationAnswers.model_validate({"salary": {**liquido, "basis": "gross"}}),
    )
    assert gross.pay == "2000000"
    assert "sueldo  ADD  2000000 CLP/month" in gross.lines


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
