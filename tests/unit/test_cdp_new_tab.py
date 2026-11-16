"""CDP attach gives up on time and never drives the tab the person already had open."""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from jobbot.browser.cdp import CdpAttachTimeout
from jobbot.browser.session import BrowserSession, BrowserTimeouts
from jobbot.config import JobbotConfig
from jobbot.exit_codes import GENERIC_FAILURE

CDP = "http://127.0.0.1:9222"


class _Page:
    def __init__(self, url: str) -> None:
        self.url = url
        self.gotos: list[str] = []
        self.closed = False

    def goto(self, url: str, **_kwargs: object) -> None:
        self.gotos.append(url)
        self.url = url

    def close(self) -> None:
        self.closed = True


class _Context:
    def __init__(self, existing: _Page) -> None:
        self.pages = [existing]
        self.opened: list[_Page] = []

    def new_page(self) -> _Page:
        page = _Page("about:blank")
        self.opened.append(page)
        self.pages.append(page)
        return page

    def set_default_navigation_timeout(self, _ms: int) -> None:
        return None

    def set_default_timeout(self, _ms: int) -> None:
        return None

    def close(self) -> None:
        return None

    def expect_page(self, timeout: int = 0) -> object:
        class _Entered:
            def __enter__(self) -> object:
                return self

            def __exit__(self, *_args: object) -> bool:
                return False

        return _Entered()


class _Cdp:
    def send(self, *_args: object, **_kwargs: object) -> None:
        raise RuntimeError("no target")

    def detach(self) -> None:
        return None


class _Browser:
    def __init__(self, context: _Context) -> None:
        self.contexts = [context]

    def new_browser_cdp_session(self) -> _Cdp:
        return _Cdp()

    def close(self) -> None:
        return None


class _Hang:
    def connect_over_cdp(self, _url: str) -> None:
        time.sleep(30)


class _Playwright:
    def __init__(self, chromium: object) -> None:
        self.chromium = chromium

    def stop(self) -> None:
        return None


class _Manager:
    def __init__(self, chromium: object) -> None:
        self._chromium = chromium

    def start(self) -> _Playwright:
        return _Playwright(self._chromium)


def test_hung_attach_raises_within_the_configured_budget(tmp_path: Path) -> None:
    session = BrowserSession(
        tmp_path,
        cdp_url=CDP,
        channel=None,
        timeouts=BrowserTimeouts(cdp_connect_ms=200),
    )
    started = time.monotonic()
    with pytest.raises(CdpAttachTimeout) as exc, pytest.MonkeyPatch.context() as patch:
        patch.setattr("jobbot.browser.session.sync_playwright", lambda: _Manager(_Hang()))
        with session:
            pass
    elapsed = time.monotonic() - started
    assert elapsed < 1
    assert "127.0.0.1:9222" in str(exc.value)
    assert "chrome-debug" in str(exc.value)


def test_attach_opens_its_own_tab_and_closes_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = _Page("https://example.test/form")
    context = _Context(existing)
    browser = _Browser(context)

    class _Ready:
        def connect_over_cdp(self, _url: str) -> _Browser:
            return browser

    monkeypatch.setattr("jobbot.browser.session.sync_playwright", lambda: _Manager(_Ready()))
    from jobbot.adapters.linkedin.client import LinkedInAdapter

    adapter = LinkedInAdapter(JobbotConfig(root=tmp_path), cdp_url=CDP)
    assert adapter.session_valid() is True
    assert existing.gotos == []
    assert existing.closed is False
    assert context.opened
    assert context.opened[0].closed is True
    assert context.opened[0].gotos


def test_linkedin_status_says_unreachable_when_attach_times_out(
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
    monkeypatch.chdir(tmp_path)

    def _timeout(*_args: object, **_kwargs: object) -> None:
        raise CdpAttachTimeout(CDP, 0.2)

    monkeypatch.setattr("jobbot.browser.cdp.connect_cdp", _timeout)
    from jobbot.cli import run_cli

    code = run_cli(["linkedin", "status", "--cdp", CDP], standalone_mode=False)
    err = capsys.readouterr().err
    assert code == GENERIC_FAILURE
    assert "unreachable" in err
    assert "not authenticated" not in err
    assert "127.0.0.1:9222" in err
