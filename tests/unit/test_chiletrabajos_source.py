"""Chiletrabajos HTML search: dates, robots, dedupe. No network."""

from __future__ import annotations

import io
import json
import urllib.error
import urllib.request
from datetime import datetime
from email.message import Message
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml

from jobbot.adapters.chiletrabajos.discover import USER_AGENT, fetch_public
from jobbot.adapters.chiletrabajos.parse import job_from_detail
from jobbot.cli import run_cli
from jobbot.portals.detect import JOB_BOARD_KINDS, AtsKind, detect_ats

FIXTURES = Path("tests/fixtures/chiletrabajos")
SANTIAGO = ZoneInfo("America/Santiago")
POSTED = datetime(2026, 10, 8, 12, 32, 54, tzinfo=SANTIAGO)
CLOSES = datetime(2026, 12, 22, 23, 59, 59, tzinfo=SANTIAGO)
OFFER = "https://www.chiletrabajos.cl/trabajo/cargo-ficticio-1234"


def _workspace(tmp_path: Path, project_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = tmp_path / "data"
    data.mkdir()
    (tmp_path / "output").mkdir()
    example = project_root / "data" / "profile.example.yaml"
    raw = yaml.safe_load(example.read_text(encoding="utf-8"))
    (data / "profile.yaml").write_text(
        yaml.safe_dump(raw, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)


def _install(monkeypatch: pytest.MonkeyPatch, fetch: object) -> None:
    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("socket")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    monkeypatch.setattr("jobbot.adapters.chiletrabajos.discover.fetch_public", fetch)
    monkeypatch.setattr("jobbot.adapters.chiletrabajos.discover.pause", lambda: None)


def _text(project_root: Path, name: str) -> str:
    return (project_root / FIXTURES / name).read_text(encoding="utf-8")


def _pages(project_root: Path) -> dict[str, str]:
    return {
        "page1": _text(project_root, "search_page1.html"),
        "page2": _text(project_root, "search_page2.html"),
        "3911436": _text(project_root, "detail_expira.html"),
        "3912000": _text(project_root, "detail_confidencial.html"),
        "3800000": _text(project_root, "detail_expired.html"),
        "expired-list": _text(project_root, "search_expired.html"),
        "changed": _text(project_root, "search_layout_changed.html"),
    }


def test_dry_run_uses_the_filter_and_writes_nothing(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    pages = _pages(project_root)
    calls: list[str] = []

    def fetch(url: str) -> tuple[int, str, str]:
        calls.append(url)
        if "/partners" in url or "/ofertasmuchomas" in url:
            raise AssertionError(url)
        if "pagina=2" in url:
            return 200, pages["page2"], url
        if "encuentra-un-empleo" in url:
            return 200, pages["page1"], url
        if "3911436" in url:
            return 200, pages["3911436"], url
        if "3912000" in url:
            return 200, pages["3912000"], url
        raise AssertionError(url)

    _install(monkeypatch, fetch)
    code = run_cli(
        ["jobs", "discover", "--source", "chiletrabajos", "--query", "abogado", "--dry-run"],
        standalone_mode=False,
    )
    captured = capsys.readouterr()
    assert code == 0
    assert "2=abogado" in calls[0]
    assert "f=2" in calls[0]
    assert "Health advisor" in captured.out
    assert "Empresa Ejemplo" in captured.out
    assert "Santiago" in captured.out
    assert "Nothing written." in captured.out
    assert not any("/partners" in url or "/ofertasmuchomas" in url for url in calls)
    job = job_from_detail(
        pages["3911436"],
        url="https://www.chiletrabajos.cl/trabajo/health-advisor-3911436",
        fallback_title="Health advisor",
    )
    assert job is not None
    assert job.url == "https://www.chiletrabajos.cl/trabajo/health-advisor-3911436"
    assert job.posted_at == POSTED
    assert job.closes_at == CLOSES
    hidden = job_from_detail(
        pages["3912000"],
        url="https://www.chiletrabajos.cl/trabajo/office-analyst-3912000",
        fallback_title="Office analyst",
    )
    assert hidden is not None
    assert hidden.company == "Confidencial"
    assert list((tmp_path / "output" / "jobs").glob("*/job.json")) == []


def test_an_expired_posting_is_not_stored(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    pages = _pages(project_root)

    def fetch(url: str) -> tuple[int, str, str]:
        if "3800000" in url:
            return 200, pages["3800000"], url
        return 200, pages["expired-list"], url

    _install(monkeypatch, fetch)
    code = run_cli(
        ["jobs", "discover", "--source", "chiletrabajos", "--query", "abogado"],
        standalone_mode=False,
    )
    assert code == 0
    assert list((tmp_path / "output" / "jobs").glob("*/job.json")) == []


def test_user_agent_is_not_a_blocked_crawler(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[urllib.request.Request] = []

    class _Response:
        status = 200

        def read(self) -> bytes:
            return b"ok"

        def geturl(self) -> str:
            return "https://www.chiletrabajos.cl/encuentra-un-empleo"

        def __enter__(self) -> _Response:
            return self

        def __exit__(self, *_args: object) -> bool:
            return False

    def urlopen(request: urllib.request.Request, timeout: int = 30) -> _Response:
        del timeout
        captured.append(request)
        return _Response()

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    monkeypatch.setattr("jobbot.adapters.chiletrabajos.discover.pause", lambda: None)
    fetch_public("https://www.chiletrabajos.cl/encuentra-un-empleo")
    agent = captured[0].get_header("User-agent") or ""
    assert agent == USER_AGENT
    assert "scrapy" not in agent.casefold()
    assert "proximic" not in agent.casefold()
    with pytest.raises(ValueError, match="robots.txt"):
        fetch_public("https://www.chiletrabajos.cl/partners/secret")


def test_rediscovery_updates_one_row(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    pages = _pages(project_root)

    def fetch(url: str) -> tuple[int, str, str]:
        if "pagina=2" in url:
            return 200, pages["page2"], url
        if "encuentra-un-empleo" in url:
            return 200, pages["page1"], url
        if "3911436" in url:
            return 200, pages["3911436"], url
        raise AssertionError(url)

    _install(monkeypatch, fetch)
    first = run_cli(
        [
            "jobs",
            "discover",
            "--source",
            "chiletrabajos",
            "--query",
            "abogado",
            "--limit",
            "1",
        ],
        standalone_mode=False,
    )
    stored = list((tmp_path / "output" / "jobs").glob("*/job.json"))
    assert first == 0
    assert len(stored) == 1
    before = json.loads(stored[0].read_text(encoding="utf-8"))["discovered_at"]
    second = run_cli(
        [
            "jobs",
            "discover",
            "--source",
            "chiletrabajos",
            "--query",
            "abogado",
            "--limit",
            "1",
        ],
        standalone_mode=False,
    )
    again = list((tmp_path / "output" / "jobs").glob("*/job.json"))
    assert second == 0
    assert len(again) == 1
    after = json.loads(again[0].read_text(encoding="utf-8"))
    assert after["source_job_id"] == "3911436"
    assert after["discovered_at"] != before


def test_learning_an_offer_stays_a_board(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert detect_ats(OFFER) is AtsKind.CHILETRABAJOS
    assert AtsKind.CHILETRABAJOS in JOB_BOARD_KINDS
    _workspace(tmp_path, project_root, monkeypatch)

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("socket")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    code = run_cli(["companies", "learn", OFFER, "--company", "Acme"], standalone_mode=False)
    captured = capsys.readouterr()
    assert code == 0
    assert "Not company-specific" in captured.out
    assert not (tmp_path / "data" / "companies.yaml").exists()


def test_an_http_error_is_its_status_not_a_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    def urlopen(request: urllib.request.Request, timeout: int = 30) -> object:
        del request, timeout
        raise urllib.error.HTTPError(OFFER, 404, "Not Found", Message(), io.BytesIO(b"gone"))

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)
    monkeypatch.setattr("jobbot.adapters.chiletrabajos.discover.pause", lambda: None)
    assert fetch_public(OFFER) == (404, "gone", OFFER)


def test_a_broken_ficha_keeps_the_other_rows(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    pages = _pages(project_root)

    def fetch(url: str) -> tuple[int, str, str]:
        if "pagina=2" in url:
            return 200, pages["page2"], url
        if "encuentra-un-empleo" in url:
            return 200, pages["page1"], url
        if "3911436" in url:
            return 200, pages["3911436"], url
        return 200, "<html><body><h1>Office analyst</h1></body></html>", url

    _install(monkeypatch, fetch)
    code = run_cli(
        ["jobs", "discover", "--source", "chiletrabajos", "--query", "abogado"],
        standalone_mode=False,
    )
    stored = list((tmp_path / "output" / "jobs").glob("*/job.json"))
    assert code == 5
    assert len(stored) == 1
    assert json.loads(stored[0].read_text(encoding="utf-8"))["source_job_id"] == "3911436"


def test_no_details_reads_the_listing_only(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    pages = _pages(project_root)

    def fetch(url: str) -> tuple[int, str, str]:
        if "/trabajo/" in url:
            raise AssertionError(url)
        if "pagina=2" in url:
            return 200, pages["page2"], url
        return 200, pages["page1"], url

    _install(monkeypatch, fetch)
    code = run_cli(
        [
            "jobs",
            "discover",
            "--source",
            "chiletrabajos",
            "--query",
            "abogado",
            "--no-details",
            "--limit",
            "1",
        ],
        standalone_mode=False,
    )
    stored = list((tmp_path / "output" / "jobs").glob("*/job.json"))
    assert code == 0
    assert len(stored) == 1
    row = json.loads(stored[0].read_text(encoding="utf-8"))
    assert row["title"] == "Health advisor"
    assert row["company"] == "Empresa Ejemplo"


def test_a_listing_without_jobs_exits_5(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    page = _text(project_root, "search_layout_changed.html")

    def fetch(url: str) -> tuple[int, str, str]:
        return 200, page, url

    _install(monkeypatch, fetch)
    code = run_cli(
        ["jobs", "discover", "--source", "chiletrabajos", "--query", "abogado", "--dry-run"],
        standalone_mode=False,
    )
    assert code == 5
