"""An uncleared Indeed challenge is exit 4, not an empty search."""

from __future__ import annotations

from pathlib import Path
from types import TracebackType

import pytest

from jobbot.adapters.indeed.jobs import IndeedChallengePending, IndeedJobSource
from jobbot.config import JobbotConfig, PathsConfig
from jobbot.exit_codes import MANUAL_CHALLENGE
from jobbot.jobs.sources import JobSearchQuery

_CARD = """
<html><body>
  <article data-testid="job-card" data-jk="8a5fab1a7c476a97">
    <h2 data-testid="job-title">Coordinador</h2>
    <div data-testid="company-name">Servicio Neutro</div>
    <div data-testid="text-location">Santiago</div>
    <a href="/viewjob?jk=8a5fab1a7c476a97">View</a>
  </article>
</body></html>
"""


class _Page:
    url = "https://cl.indeed.com/"

    def goto(self, url: str, **_: object) -> None:
        self.url = url

    def content(self) -> str:
        return _CARD


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


def _source(tmp_path: Path) -> IndeedJobSource:
    config = JobbotConfig(root=tmp_path, paths=PathsConfig())
    return IndeedJobSource(config)


def test_an_uncleared_search_challenge_is_not_an_empty_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(IndeedJobSource, "_session", lambda _self: _Session())
    monkeypatch.setattr(
        IndeedJobSource,
        "_clear_challenge",
        lambda _self, _browser, context: False,
    )

    with pytest.raises(IndeedChallengePending) as raised:
        _source(tmp_path).search_cards(JobSearchQuery(query="coordinador", limit=1))

    assert raised.value.context == "search results"


def test_an_uncleared_detail_challenge_stops_the_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(IndeedJobSource, "_session", lambda _self: _Session())

    def clear(_self: IndeedJobSource, _browser: object, *, context: str) -> bool:
        return context != "job detail"

    monkeypatch.setattr(IndeedJobSource, "_clear_challenge", clear)

    with pytest.raises(IndeedChallengePending) as raised:
        _source(tmp_path).search_jobs(JobSearchQuery(query="coordinador", limit=1))

    assert raised.value.context == "job detail"


def test_jobs_search_exits_4_and_does_not_say_there_are_no_jobs(
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

    def boom(_self: IndeedJobSource, _query: JobSearchQuery) -> list[object]:
        raise IndeedChallengePending("search results")

    monkeypatch.setattr(IndeedJobSource, "search_jobs", boom)
    from jobbot.cli import run_cli

    code = run_cli(["jobs", "search", "coordinador"], standalone_mode=False)
    captured = capsys.readouterr()

    assert code == MANUAL_CHALLENGE
    assert "was not cleared" in captured.err
    assert "No jobs found" not in captured.err
    assert "No jobs found" not in captured.out
