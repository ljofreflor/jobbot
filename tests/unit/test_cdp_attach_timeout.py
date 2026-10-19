"""A hung CDP attach stays on that Chrome: no second browser, no orphan package."""

from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest
import yaml
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

from jobbot.browser.cdp import DEFAULT_CDP_ATTACH_S, CdpAttachTimeout, connect_cdp
from jobbot.cli import run_cli
from jobbot.exit_codes import GENERIC_FAILURE

CDP = "http://127.0.0.1:9222"
ATS_URL = "https://boards.greenhouse.io/acme/jobs/1"


def _workspace(tmp_path: Path, project_root: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    (tmp_path / "data").mkdir()
    (tmp_path / "output").mkdir()
    (tmp_path / "data" / "profile.yaml").write_text(
        (project_root / "data" / "profile.example.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (tmp_path / ".jobbot.toml").write_text(
        f'[paths]\ntemplates = "{project_root / "templates"}"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("typer.confirm", lambda *_a, **_k: True)
    monkeypatch.setattr("jobbot.cli._fetch_public_html", lambda _url: None)
    monkeypatch.setattr(
        "jobbot.jobs.closure.fetch_posting_text",
        lambda _url, **_k: "<html>still open</html>",
    )
    import jobbot.cli as cli
    from jobbot.db.engine import make_engine, make_session_factory
    from jobbot.jobs.repository import JobRepository
    from jobbot.models.job import JobPosting

    config = cli.load_config()
    session = make_session_factory(make_engine(config.database_path))()
    stored = JobRepository(session).upsert_external(
        JobPosting.model_validate(
            {
                "id": "PENDING",
                "source": "manual",
                "title": "Un cargo",
                "company": "Acme",
                "url": ATS_URL,
                "ats_url": ATS_URL,
                "ats_kind": "greenhouse",
                "description": "Una descripción.",
            }
        )
    )
    session.commit()
    return stored.id


class _Hang:
    """A Chrome that never answers: Playwright's driver enforces the deadline."""

    def connect_over_cdp(self, url: str, *, timeout: float) -> None:
        time.sleep(timeout / 1000)
        raise PlaywrightTimeoutError(f"Timeout {timeout:g}ms exceeded.")


class _Interrupt:
    def connect_over_cdp(self, url: str, *, timeout: float) -> None:
        raise KeyboardInterrupt


class _Playwright:
    def __init__(self, chromium: object) -> None:
        self.chromium = chromium

    def stop(self) -> None:
        raise AssertionError("stop() can wait on the abandoned attach")


class _Manager:
    def __init__(self, chromium: object) -> None:
        self._chromium = chromium

    def start(self) -> _Playwright:
        return _Playwright(self._chromium)


def _forbid_browser(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    opened: list[str] = []

    def refuse(url: str, **_k: object) -> str:
        opened.append(url)
        raise AssertionError(url)

    monkeypatch.setattr("jobbot.browser.background.open_url", refuse)
    monkeypatch.setattr("webbrowser.open", refuse)
    return opened


def test_default_attach_budget_is_fifteen_seconds() -> None:
    assert DEFAULT_CDP_ATTACH_S == 15


def test_attach_runs_on_the_thread_that_started_playwright() -> None:
    """The sync API is bound to that thread: a worker thread never connects."""

    class _Chromium:
        def __init__(self) -> None:
            self.thread: int | None = None
            self.timeout: float | None = None

        def connect_over_cdp(self, url: str, *, timeout: float) -> str:
            self.thread = threading.get_ident()
            self.timeout = timeout
            return "browser"

    chromium = _Chromium()

    assert connect_cdp(chromium, CDP, timeout_s=3) == "browser"
    assert chromium.thread == threading.get_ident()
    assert chromium.timeout == 3000, "the deadline is the driver's own"


def test_playwright_timeout_becomes_the_attach_timeout() -> None:
    with pytest.raises(CdpAttachTimeout) as caught:
        connect_cdp(_Hang(), CDP, timeout_s=0.01)

    assert "127.0.0.1:9222" in str(caught.value)


def test_hung_attach_exits_without_another_browser_or_orphan_package(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    job_id = _workspace(tmp_path, project_root, monkeypatch)
    opened = _forbid_browser(monkeypatch)
    monkeypatch.setattr(
        "playwright.sync_api.sync_playwright",
        lambda: _Manager(_Hang()),
    )
    started = time.monotonic()
    code = run_cli(
        [
            "application",
            "apply",
            job_id,
            "--apply",
            "--yes",
            "--cdp",
            CDP,
            "--cdp-timeout",
            "0.2",
        ],
        standalone_mode=False,
    )
    elapsed = time.monotonic() - started
    captured = capsys.readouterr()
    mirrors = list((tmp_path / "output" / "ops" / "failures").glob("*.json"))

    assert code == GENERIC_FAILURE
    assert elapsed < 2
    assert opened == []
    assert "Falling back" not in captured.err
    assert "127.0.0.1:9222" in captured.err
    assert list(tmp_path.glob("output/jobs/*/application")) == []
    assert mirrors
    text = mirrors[0].read_text(encoding="utf-8")
    assert "127.0.0.1:9222" in text
    assert "CdpAttach" in text
    profile = yaml.safe_load(
        (project_root / "data" / "profile.example.yaml").read_text(encoding="utf-8")
    )
    assert profile["personal"]["email"] not in text
    assert profile["personal"]["name"] not in text


def test_interrupt_during_attach_records_and_opens_nothing(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    job_id = _workspace(tmp_path, project_root, monkeypatch)
    opened = _forbid_browser(monkeypatch)
    monkeypatch.setattr(
        "playwright.sync_api.sync_playwright",
        lambda: _Manager(_Interrupt()),
    )
    code = run_cli(
        ["application", "apply", job_id, "--apply", "--yes", "--cdp", CDP, "--cdp-timeout", "2"],
        standalone_mode=False,
    )
    capsys.readouterr()

    assert code == GENERIC_FAILURE
    assert opened == []
    assert list(tmp_path.glob("output/jobs/*/application")) == []
    text = (tmp_path / "output" / "ops" / "failures").joinpath(
        next((tmp_path / "output" / "ops" / "failures").glob("*.json")).name
    ).read_text(encoding="utf-8")
    assert "interrupted" in text.casefold()
    assert "127.0.0.1:9222" in text


def test_hung_search_is_not_an_empty_result(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "output").mkdir()
    (tmp_path / "data" / "profile.yaml").write_text(
        (project_root / "data" / "profile.example.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "jobbot.browser.session.sync_playwright",
        lambda: _Manager(_Hang()),
    )
    started = time.monotonic()
    code = run_cli(
        ["jobs", "search", "editor", "--no-enrich", "--cdp", CDP, "--cdp-timeout", "0.2"],
        standalone_mode=False,
    )
    elapsed = time.monotonic() - started
    captured = capsys.readouterr()

    assert code == GENERIC_FAILURE
    assert elapsed < 2
    assert "No jobs found" not in captured.out
    assert "127.0.0.1:9222" in captured.err
