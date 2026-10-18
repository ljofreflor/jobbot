"""Indeed no longer has a structured resume editor (issue #278)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from types import TracebackType

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from typer.testing import CliRunner

from jobbot.adapters.diff_engine import load_snapshot, save_snapshot
from jobbot.adapters.indeed.client import IndeedAdapter, indeed_session_authenticated
from jobbot.adapters.indeed.resume_edit import (
    DOCUMENT_ONLY_MESSAGE,
    IndeedUiChanged,
    load_editor_state,
    record_editor_state,
    resume_editor_state,
    set_headline_via_contact,
)
from jobbot.cli import app
from jobbot.config import JobbotConfig, PathsConfig
from jobbot.cv.status import PresenceState, _indeed
from jobbot.exit_codes import AUTH_REQUIRED, UI_CHANGED
from jobbot.models.external_profile import ExternalExperience, ExternalProfile
from jobbot.models.sync import SyncOperation, SyncOpType, SyncPlan
from jobbot.profile.loader import load_profile

DOCUMENT_URL = "https://profile.indeed.com/document/view"
STRUCTURED_HTML = '<div data-testid="skills-section"></div>'


def test_resume_editor_state_three_ways(project_root: Path) -> None:
    document = (project_root / "tests/fixtures/indeed/document_view.html").read_text(
        encoding="utf-8"
    )
    assert resume_editor_state(DOCUMENT_URL, document) == "document_only"
    assert resume_editor_state("https://profile.indeed.com/resume", document) == "document_only"
    assert resume_editor_state("https://profile.indeed.com/resume", STRUCTURED_HTML) == "structured"
    assert resume_editor_state("https://profile.indeed.com/resume", "<html></html>") == "unknown"


class _Ctx:
    def __init__(self, page: object) -> None:
        self.page = page

    def __enter__(self) -> _Ctx:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        return None

    def dump_debug(self, _component: str, _reason: str) -> None:
        return None


class _DocumentPage:
    def __init__(self, html: str) -> None:
        self.url = DOCUMENT_URL
        self._html = html

    def goto(self, url: str, **_: object) -> None:
        self.url = DOCUMENT_URL if "resume" in url else url

    def wait_for_selector(self, selector: str, timeout: float | None = None) -> None:
        raise PlaywrightTimeout(selector)

    def wait_for_timeout(self, _ms: float) -> None:
        return None

    def content(self) -> str:
        return self._html

    def inner_text(self, _selector: str) -> str:
        return "CV Preferencias"


def _adapter(tmp_path: Path, project_root: Path) -> IndeedAdapter:
    profile_path = tmp_path / "data" / "profile.yaml"
    profile_path.parent.mkdir(parents=True, exist_ok=True)
    profile_path.write_text(
        (project_root / "data/profile.example.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    return IndeedAdapter(JobbotConfig(root=tmp_path, paths=PathsConfig(output=Path("output"))))


def test_pull_document_view_keeps_the_previous_snapshot(tmp_path: Path, project_root: Path) -> None:
    adapter = _adapter(tmp_path, project_root)
    html = (project_root / "tests/fixtures/indeed/document_view.html").read_text(encoding="utf-8")
    saved = save_snapshot(
        ExternalProfile(
            source="indeed",
            headline="Titular guardado",
            experience=[ExternalExperience(company="Acme Analytics", title="Analista")],
        ),
        adapter.config.output_dir,
    )
    before = hashlib.sha256(saved.read_bytes()).hexdigest()
    adapter._session = lambda: _Ctx(_DocumentPage(html))  # type: ignore[method-assign]

    with pytest.raises(IndeedUiChanged, match="document/view"):
        adapter.pull_and_save()

    assert hashlib.sha256(saved.read_bytes()).hexdigest() == before
    assert load_editor_state(adapter.config.output_dir) == "document_only"
    assert load_profile(adapter.config.profile_path).personal.name == "Ana Ejemplo"


def test_indeed_pull_cli_exits_ui_changed(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(self: IndeedAdapter) -> Path:
        raise IndeedUiChanged(DOCUMENT_ONLY_MESSAGE)

    monkeypatch.setattr(IndeedAdapter, "pull_and_save", _boom)
    result = CliRunner().invoke(app, ["indeed", "pull"])
    assert result.exit_code == UI_CHANGED
    assert "document/view" in result.output


def test_status_says_structured_cv_is_gone_not_pending_ops(
    tmp_path: Path, project_root: Path
) -> None:
    adapter = _adapter(tmp_path, project_root)
    save_snapshot(
        ExternalProfile(source="indeed", headline=None, experience=[], skills=[]),
        adapter.config.output_dir,
    )
    candidate = load_profile(adapter.config.profile_path)
    record_editor_state(adapter.config.output_dir, "document_only")
    row = _indeed(adapter.config, candidate)
    assert row.evidence == "sin CV estructurado"
    assert row.state is not PresenceState.BEHIND
    assert "sync ops" not in row.evidence


class _Silent:
    def count(self) -> int:
        return 0

    def nth(self, _index: int) -> _Silent:
        return self

    def fill(self, _value: str) -> None:
        raise AssertionError("filled an input")

    def click(self, **_kwargs: object) -> None:
        raise AssertionError("clicked")


class _ContactPage:
    def __init__(self, html: str) -> None:
        self.url = "https://profile.indeed.com/edit/contact"
        self._html = html
        self.fills: list[str] = []
        self.clicks: list[str] = []

    def goto(self, url: str, **_: object) -> None:
        self.url = url

    def wait_for_timeout(self, _ms: float) -> None:
        return None

    def content(self) -> str:
        return self._html

    def get_by_test_id(self, _testid: str) -> _Silent:
        return _Silent()

    def get_by_label(self, _name: str, exact: bool = False) -> _Silent:
        return _Silent()

    def get_by_role(self, *_args: object, **_kwargs: object) -> _Silent:
        return _Silent()


def test_headline_without_title_label_does_not_write(
    project_root: Path,
) -> None:
    html = (project_root / "tests/fixtures/indeed/contact_edit_no_title.html").read_text(
        encoding="utf-8"
    )
    page = _ContactPage(html)
    with pytest.raises(IndeedUiChanged, match="Título"):
        set_headline_via_contact(page, "Titular que no debe guardarse")  # type: ignore[arg-type]
    assert page.fills == []
    assert page.clicks == []


class _Loc:
    def __init__(self, page: _RecordingPage, key: str) -> None:
        self.page = page
        self.key = key

    def count(self) -> int:
        return 0 if self.key == "skills-section" else 1

    def fill(self, value: str) -> None:
        self.page.fills.append((self.key, value))

    def click(self, **_kwargs: object) -> None:
        self.page.clicks.append(self.key)

    def first(self) -> _Loc:
        return self

    def locator(self, selector: str) -> _Loc:
        return _Loc(self.page, selector)

    def inner_text(self) -> str:
        return ""

    def all_text_contents(self) -> list[str]:
        return []


class _RecordingPage:
    def __init__(self) -> None:
        self.url = "https://profile.indeed.com/resume"
        self.fills: list[tuple[str, str]] = []
        self.clicks: list[str] = []
        self.gotos: list[str] = []
        self.keyboard = self

    def goto(self, url: str, **_: object) -> None:
        self.gotos.append(url)
        self.url = url

    def wait_for_timeout(self, _ms: float) -> None:
        return None

    def wait_for_selector(self, _selector: str, timeout: float | None = None) -> None:
        return None

    def content(self) -> str:
        return STRUCTURED_HTML

    def inner_text(self, _selector: str) -> str:
        return ""

    def get_by_test_id(self, testid: str) -> _Loc:
        return _Loc(self, testid)

    def get_by_role(self, role: str, name: str | None = None) -> _Loc:
        return _Loc(self, f"{role}:{name}")

    def get_by_label(self, name: str, exact: bool = False) -> _Loc:
        return _Loc(self, f"label:{name}")

    def press(self, _key: str) -> None:
        return None


def test_sync_section_skills_writes_only_skills(tmp_path: Path, project_root: Path) -> None:
    adapter = _adapter(tmp_path, project_root)
    page = _RecordingPage()
    adapter._session = lambda: _Ctx(page)  # type: ignore[method-assign]
    plan = SyncPlan(
        target="indeed",
        operations=[
            SyncOperation(op=SyncOpType.ADD, section="skills", field="name", label="python")
        ],
    )
    adapter.apply_sync_plan(plan, section="skills")
    assert page.fills
    assert {key for key, _value in page.fills} == {"skill-name-input-autocomplete-input"}
    blocked = ("/edit/contact", "/experience/", "/education/")
    assert not any(piece in url for url in page.gotos for piece in blocked)


def test_unreadable_headline_is_not_verified(tmp_path: Path, project_root: Path) -> None:
    adapter = _adapter(tmp_path, project_root)
    rendered = (project_root / "tests/fixtures/indeed_resume_sections.html").read_text(
        encoding="utf-8"
    )

    class _Rendered:
        def __init__(self) -> None:
            self.url = "https://profile.indeed.com/resume"
            self.rendered = False

        def goto(self, url: str, **_: object) -> None:
            self.url = url

        def wait_for_selector(self, _selector: str, timeout: float | None = None) -> None:
            self.rendered = True

        def wait_for_timeout(self, _ms: float) -> None:
            return None

        def content(self) -> str:
            return rendered if self.rendered else "<html></html>"

        def inner_text(self, _selector: str) -> str:
            return ""

    result = adapter._snapshot_after(  # noqa: SLF001
        _Ctx(_Rendered()),
        load_profile(adapter.config.profile_path),
        SyncPlan(target="indeed", operations=[]),
        "20261018T000000Z",
        edit_verified=True,
    )
    stored = load_snapshot(adapter.config.output_dir, "indeed")
    assert stored is not None
    assert stored.headline is None
    assert result.verified is False


def test_ctk_alone_is_not_a_session() -> None:
    assert (
        indeed_session_authenticated(
            url="https://profile.indeed.com/",
            html="<html><body>Indeed</body></html>",
            cookie_names=["CTK"],
        )
        is False
    )
    assert (
        indeed_session_authenticated(
            url="https://profile.indeed.com/",
            html='<div data-testid="account-menu">Cuenta</div>',
            cookie_names=["CTK"],
        )
        is True
    )


def test_session_valid_with_only_ctk(tmp_path: Path, project_root: Path) -> None:
    adapter = _adapter(tmp_path, project_root)

    class _Home:
        def __init__(self) -> None:
            self.url = "https://secure.indeed.com/account/login"

        def goto(self, url: str, **_: object) -> None:
            self.url = url

        def content(self) -> str:
            return "<html><body>Indeed</body></html>"

        @property
        def context(self) -> object:
            return self

        def cookies(self) -> list[dict[str, str]]:
            return [{"name": "CTK", "value": "visitor"}]

    adapter._session = lambda: _Ctx(_Home())  # type: ignore[method-assign]
    assert adapter.session_valid() is False


def test_indeed_status_cli_exits_auth_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(IndeedAdapter, "session_valid", lambda self: False)
    result = CliRunner().invoke(app, ["indeed", "status"])
    assert result.exit_code == AUTH_REQUIRED
    assert "not authenticated" in result.output
