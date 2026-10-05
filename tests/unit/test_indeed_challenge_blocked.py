"""Unresolved Indeed anti-bot challenges are a block, not an empty search (#184)."""

from __future__ import annotations

import io
import time
from pathlib import Path
from typing import Any

import pytest
from rich.console import Console

from jobbot.adapters.indeed.jobs import (
    ChallengeBlocked,
    IndeedJobSource,
    challenge_wait_seconds,
)
from jobbot.config import JobbotConfig
from jobbot.exit_codes import MANUAL_CHALLENGE, SUCCESS
from jobbot.jobs.sources import JobSearchQuery
from jobbot.ops.failures import should_record_cli_failure

CHALLENGE_HTML = """
<title>Security Check</title>
<script>window.INDEED_CLOUDFLARE_STATIC_PAGE={PAGE_TYPE:"captcha"};</script>
<div class="challenge-platform">Verificación adicional requerida</div>
"""

SEARCH_HTML = """
<article data-testid="job-card" data-jk="aaa111bbb222">
  <h2 data-testid="job-title">Epidemióloga clínica</h2>
  <div data-testid="company-name">Servicio Ficticio</div>
  <a href="/viewjob?jk=aaa111bbb222">Ver</a>
</article>
<article data-testid="job-card" data-jk="ccc333ddd444">
  <h2 data-testid="job-title">Enfermera de vigilancia</h2>
  <div data-testid="company-name">Hospital Ficticio</div>
  <a href="/viewjob?jk=ccc333ddd444">Ver</a>
</article>
"""


class FakePage:
    def __init__(self, html: str) -> None:
        self.html = html
        self.url = "https://cl.indeed.com/jobs"
        self.gotos: list[str] = []

    def goto(self, url: str, **_kwargs: object) -> None:
        self.gotos.append(url)
        self.url = url
        if "viewjob" in url:
            self.html = CHALLENGE_HTML

    def content(self) -> str:
        return self.html


class FakeBrowser:
    def __init__(self, page: FakePage) -> None:
        self.page = page
        self.pauses: list[float] = []
        self.debug: list[str] = []

    def __enter__(self) -> FakeBrowser:
        return self

    def __exit__(self, *_exc: object) -> bool:
        return False

    def pause_for_manual(self, _reason: str, *, is_clear: Any, timeout_seconds: float) -> bool:
        self.pauses.append(timeout_seconds)
        return bool(is_clear())

    def dump_debug(self, *_a: object, **_k: object) -> None:
        self.debug.append("dump")


def test_challenge_wait_is_zero_without_a_tty() -> None:
    assert challenge_wait_seconds(None, stdin_is_tty=False) == 0.0
    assert challenge_wait_seconds(None, stdin_is_tty=True) == 300.0
    assert challenge_wait_seconds(0, stdin_is_tty=True) == 0.0


def test_search_challenge_without_tty_fails_fast(tmp_path: Path) -> None:
    source = IndeedJobSource(JobbotConfig(root=tmp_path), challenge_wait=0)
    page = FakePage(CHALLENGE_HTML)
    browser = FakeBrowser(page)
    source._session = lambda: browser  # type: ignore[method-assign]
    started = time.monotonic()
    with pytest.raises(ChallengeBlocked, match="verificación anti-bot"):
        source.search_jobs(JobSearchQuery(query="enfermera", location="Santiago", limit=5))
    assert time.monotonic() - started < 1.0
    assert browser.pauses == []


def test_detail_challenge_returns_cards_after_one_wait(tmp_path: Path) -> None:
    source = IndeedJobSource(JobbotConfig(root=tmp_path), challenge_wait=0)
    page = FakePage(SEARCH_HTML)
    browser = FakeBrowser(page)
    source._session = lambda: browser  # type: ignore[method-assign]
    jobs = source.search_jobs(JobSearchQuery(query="enfermera", location="Santiago", limit=5))
    assert [j.title for j in jobs] == ["Epidemióloga clínica", "Enfermera de vigilancia"]
    viewjobs = [url for url in page.gotos if "viewjob" in url]
    assert len(viewjobs) == 1


def test_empty_search_without_challenge_is_still_empty(tmp_path: Path) -> None:
    source = IndeedJobSource(JobbotConfig(root=tmp_path), challenge_wait=0)
    page = FakePage("<html><body><p>No results</p></body></html>")
    source._session = lambda: FakeBrowser(page)  # type: ignore[method-assign]
    assert source.search_jobs(JobSearchQuery(query="nada", limit=5)) == []


def _workspace(tmp_path: Path, project_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "data").mkdir(exist_ok=True)
    (tmp_path / "data" / "profile.yaml").write_text(
        (project_root / "data" / "profile.example.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)


def test_jobs_search_challenge_exits_4_not_empty(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)

    class BlockedSource:
        base = "https://cl.indeed.com"

        def __init__(self, *_a: object, **_k: object) -> None:
            pass

        def search_jobs(self, _q: JobSearchQuery) -> list[object]:
            raise ChallengeBlocked("search results")

        def search_cards(self, _q: JobSearchQuery) -> list[object]:
            raise ChallengeBlocked("search results")

    import jobbot.adapters.indeed.jobs as indeed_jobs
    import jobbot.cli as cli

    monkeypatch.setattr(indeed_jobs, "IndeedJobSource", BlockedSource)
    out, err = io.StringIO(), io.StringIO()
    monkeypatch.setattr(cli, "console", Console(file=out, color_system=None))
    monkeypatch.setattr(cli, "err_console", Console(file=err, color_system=None))
    code = cli.run_cli(
        ["jobs", "search", "enfermera", "--challenge-wait", "0"],
        standalone_mode=False,
    )
    blob = out.getvalue() + err.getvalue()
    assert code == MANUAL_CHALLENGE
    assert "No jobs found." not in blob
    assert "verificación anti-bot" in blob
    assert "chrome-debug" in blob
    assert "--park" in blob
    assert "get" in blob


def test_jobs_search_empty_without_challenge_still_says_none(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)

    class EmptySource:
        base = "https://cl.indeed.com"

        def __init__(self, *_a: object, **_k: object) -> None:
            pass

        def search_jobs(self, _q: JobSearchQuery) -> list[object]:
            return []

        def search_cards(self, _q: JobSearchQuery) -> list[object]:
            return []

    import jobbot.adapters.indeed.jobs as indeed_jobs
    import jobbot.cli as cli

    monkeypatch.setattr(indeed_jobs, "IndeedJobSource", EmptySource)
    out = io.StringIO()
    monkeypatch.setattr(cli, "console", Console(file=out, color_system=None))
    monkeypatch.setattr(cli, "err_console", Console(file=io.StringIO(), color_system=None))
    code = cli.run_cli(["jobs", "search", "nada"], standalone_mode=False)
    assert code == SUCCESS
    assert "No jobs found." in out.getvalue()


def test_manual_challenge_is_not_an_ops_defect() -> None:
    assert not should_record_cli_failure(["jobbot", "jobs", "search", "x"], MANUAL_CHALLENGE)
