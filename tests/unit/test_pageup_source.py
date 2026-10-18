"""PageUp listing pagination, UTC closing dates, and the captcha stop. No network."""

from __future__ import annotations

import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from jobbot.adapters.pageup.parse import allowed, canonical_job_url, parse_listing
from jobbot.cli import run_cli
from jobbot.portals.detect import AtsKind, detect_ats, detect_ats_in_html

FIXTURES = Path("tests/fixtures/pageup")
HOST = "https://jobs.unicef.org"


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


def _install(
    monkeypatch: pytest.MonkeyPatch,
    fetch: object,
) -> None:
    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("socket")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    monkeypatch.setattr("jobbot.adapters.pageup.discover.fetch_public", fetch)
    monkeypatch.setattr("jobbot.adapters.pageup.discover.pause", lambda: None)


def test_unicef_dry_run_lists_twenty_and_writes_nothing(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    page = (project_root / FIXTURES / "search_page1.html").read_text(encoding="utf-8")
    calls: list[str] = []

    def fetch(url: str) -> tuple[int, str, str]:
        calls.append(url)
        return 200, page, url

    _install(monkeypatch, fetch)
    code = run_cli(
        [
            "jobs",
            "discover",
            "--source",
            "unicef",
            "--query",
            "health",
            "--limit",
            "20",
            "--dry-run",
        ],
        standalone_mode=False,
    )
    captured = capsys.readouterr()
    assert code == 0
    assert len(calls) == 1
    assert "search-keyword=health" in calls[0]
    assert "page=2" not in calls[0]
    assert "20 avisos" in captured.out
    assert "Nothing written." in captured.out
    assert list((tmp_path / "output" / "jobs").glob("*/job.json")) == []


def test_canonical_url_drops_the_slug() -> None:
    mapped = canonical_job_url(HOST, "/en-us/job/596184/senior-fundraising-associate")
    assert mapped == (
        "https://jobs.unicef.org/en-us/job/596184/",
        "jobs.unicef.org:596184",
    )


def test_close_date_is_the_published_utc_instant(project_root: Path) -> None:
    html = (project_root / FIXTURES / "search_page1.html").read_text(encoding="utf-8")
    job = parse_listing(html, HOST, f"{HOST}/en-us/search/").jobs[0]
    assert job.closes_at == datetime(2026, 10, 23, 5, 55, tzinfo=UTC)
    assert job.source_job_id == "jobs.unicef.org:596184"


def test_more_link_fetches_the_second_page_once(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    root = project_root / FIXTURES
    pages = {
        "1": (root / "search_page1.html").read_text(encoding="utf-8"),
        "2": (root / "search_page2.html").read_text(encoding="utf-8"),
    }
    calls: list[str] = []

    def fetch(url: str) -> tuple[int, str, str]:
        calls.append(url)
        key = "2" if "page=2" in url else "1"
        return 200, pages[key], url

    _install(monkeypatch, fetch)
    assert (
        run_cli(
            ["jobs", "discover", "--source", "unicef", "--query", "health", "--limit", "50"],
            standalone_mode=False,
        )
        == 0
    )
    assert len(calls) == 2
    assert "page=2" in calls[1]
    stored = list((tmp_path / "output" / "jobs").glob("*/job.json"))
    assert len(stored) == 25


def test_the_same_id_with_another_slug_does_not_duplicate(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    slugs = iter(("senior-fundraising-associate", "fundraising-lead"))

    def fetch(url: str) -> tuple[int, str, str]:
        slug = next(slugs)
        html = (
            '<div class="list-view--item">'
            f'<a class="job-link" href="/en-us/job/596184/{slug}">Senior fundraising associate</a>'
            '<span class="close-date"><time datetime="2026-10-23T05:55:00Z"></time></span>'
            "</div>"
        )
        return 200, html, url

    _install(monkeypatch, fetch)
    args = ["jobs", "discover", "--source", "unicef", "--query", "health", "--limit", "5"]
    assert run_cli(args, standalone_mode=False) == 0
    assert run_cli(args, standalone_mode=False) == 0
    stored = list((tmp_path / "output" / "jobs").glob("*/job.json"))
    assert len(stored) == 1


def test_pageup_assets_are_detected(project_root: Path) -> None:
    html = (project_root / FIXTURES / "own_domain.html").read_text(encoding="utf-8")
    kind, _evidence = detect_ats_in_html(html)
    assert kind is AtsKind.PAGEUP
    assert detect_ats("https://secure.dc5.pageuppeople.com/apply/1") is AtsKind.PAGEUP


def test_a_captcha_listing_exits_4(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    html = (project_root / FIXTURES / "listing_captcha.html").read_text(encoding="utf-8")

    def fetch(url: str) -> tuple[int, str, str]:
        return 200, html, url

    _install(monkeypatch, fetch)
    code = run_cli(
        ["jobs", "discover", "--source", "unicef", "--query", "health", "--limit", "5"],
        standalone_mode=False,
    )
    captured = capsys.readouterr()
    assert code == 4
    assert "jobs add --file" in captured.out
    assert len(list((tmp_path / "output" / "jobs").glob("*/job.json"))) == 0


def test_a_captcha_does_not_discard_a_site_that_answered(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    challenge = (project_root / FIXTURES / "listing_captcha.html").read_text(encoding="utf-8")
    listing = (
        '<div class="list-view--item">'
        '<a class="job-link" href="/en-us/job/7/role">Role</a>'
        '<span class="close-date"><time datetime="2026-11-01T00:00:00Z"></time></span>'
        "</div>"
    )

    def fetch(url: str) -> tuple[int, str, str]:
        return 200, (challenge if "walled" in url else listing), url

    _install(monkeypatch, fetch)
    code = run_cli(
        [
            "jobs",
            "discover",
            "--source",
            "pageup",
            "--site",
            "jobs.unicef.org",
            "--site",
            "walled.pageuppeople.com",
            "--query",
            "health",
            "--limit",
            "5",
        ],
        standalone_mode=False,
    )
    assert code == 0
    assert len(list((tmp_path / "output" / "jobs").glob("*/job.json"))) == 1


def test_a_home_based_place_is_remote_but_remote_sensing_is_not() -> None:
    html = (
        '<div class="list-view--item">'
        '<a class="job-link" href="/en-us/job/1/programme-specialist">Programme specialist</a>'
        '<span class="location">Home-based</span>'
        "</div>"
        '<div class="list-view--item">'
        '<a class="job-link" href="/en-us/job/2/remote-sensing-data-engineer">'
        "Remote Sensing Data Engineer</a>"
        '<span class="location">Santiago, Chile</span>'
        "</div>"
    )
    jobs = {job.source_job_id: job for job in parse_listing(html, HOST, HOST).jobs}
    assert jobs["jobs.unicef.org:1"].remote_type == "remote"
    assert jobs["jobs.unicef.org:2"].remote_type is None


def test_an_expired_closing_is_not_stored(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)

    def fetch(url: str) -> tuple[int, str, str]:
        html = (
            '<div class="list-view--item">'
            '<a class="job-link" href="/en-us/job/1/old-role">Old role</a>'
            '<span class="close-date"><time datetime="2026-01-01T00:00:00Z"></time></span>'
            "</div>"
        )
        return 200, html, url

    _install(monkeypatch, fetch)
    assert (
        run_cli(
            ["jobs", "discover", "--source", "unicef", "--query", "health", "--limit", "5"],
            standalone_mode=False,
        )
        == 0
    )
    assert list((tmp_path / "output" / "jobs").glob("*/job.json")) == []


def test_a_disallowed_more_link_is_not_requested(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    robots = (project_root / FIXTURES / "robots.txt").read_text(encoding="utf-8")
    for line in robots.splitlines():
        if line.startswith("Disallow:"):
            path = line.split(":", 1)[1].strip()
            assert not allowed(f"https://jobs.unicef.org{path}/secret")
    assert allowed("https://jobs.unicef.org/en-us/listing/")
    calls: list[str] = []

    def fetch(url: str) -> tuple[int, str, str]:
        calls.append(url)
        html = (
            '<div class="list-view--item">'
            '<a class="job-link" href="/en-us/job/9/role">Role</a>'
            '<span class="close-date"><time datetime="2026-11-01T00:00:00Z"></time></span>'
            "</div>"
            '<a class="more-link" href="/admin/next">More</a>'
        )
        return 200, html, url

    _install(monkeypatch, fetch)
    assert (
        run_cli(
            ["jobs", "discover", "--source", "unicef", "--query", "health", "--limit", "50"],
            standalone_mode=False,
        )
        == 0
    )
    assert len(calls) == 1
    assert all("/admin" not in url for url in calls)


def test_a_path_on_the_site_is_rejected(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    code = run_cli(
        [
            "jobs",
            "discover",
            "--source",
            "pageup",
            "--site",
            "jobs.unicef.org/en-us",
            "--query",
            "health",
        ],
        standalone_mode=False,
    )
    assert code == 2
