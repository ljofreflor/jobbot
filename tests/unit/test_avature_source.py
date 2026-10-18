"""Avature SearchJobs pagination, closing dates, and the qtvc ban. No network."""

from __future__ import annotations

import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from jobbot.adapters.avature.discover import UNOPS_SITE, AvatureDiscover, blocked_qtvc
from jobbot.adapters.avature.parse import (
    ZONE_NOTE,
    apply_detail,
    canonical_job_url,
    parse_search,
    source_job_id,
)
from jobbot.cli import run_cli
from jobbot.jobs.discover import SiteStatus, SiteTarget
from jobbot.models.job import JobPosting
from jobbot.portals.detect import AtsKind, detect_ats, detect_ats_in_html

FIXTURES = Path("tests/fixtures/avature")
DETAIL = (
    "https://careers.unops.org/careersmarketplace/JobDetail/Administration-Assistant/4611"
)


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


def _pages(project_root: Path) -> dict[str, str]:
    root = project_root / FIXTURES
    return {
        "0": (root / "search_page1.html").read_text(encoding="utf-8"),
        "6": (root / "search_page2.html").read_text(encoding="utf-8"),
    }


def test_unops_dry_run_pages_twice_and_writes_nothing(
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
        offset = "6" if "jobOffset=6" in url else "0"
        return 200, pages[offset], url

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("socket")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    monkeypatch.setattr("jobbot.adapters.avature.discover.fetch_public", fetch)
    monkeypatch.setattr("jobbot.adapters.avature.discover.pause", lambda: None)
    code = run_cli(
        [
            "jobs",
            "discover",
            "--source",
            "unops",
            "--query",
            "health",
            "--limit",
            "12",
            "--dry-run",
        ],
        standalone_mode=False,
    )
    captured = capsys.readouterr()
    assert code == 0
    assert any("jobOffset=0" in url for url in calls)
    assert any("jobOffset=6" in url for url in calls)
    assert not any("jobOffset=12" in url for url in calls)
    assert "12 avisos" in captured.out
    assert "Nothing written." in captured.out
    assert list((tmp_path / "output" / "jobs").glob("*/job.json")) == []


def test_job_detail_id_drops_qtvc() -> None:
    dirty = f"{DETAIL}?qtvc=session"
    assert source_job_id(UNOPS_SITE, dirty) == (
        "careers.unops.org/careersmarketplace:4611"
    )
    assert "qtvc" not in canonical_job_url(dirty)


def test_posting_end_date_is_end_of_day_utc(project_root: Path) -> None:
    html = (project_root / FIXTURES / "job_detail_4611.html").read_text(encoding="utf-8")
    listed = parse_search(
        f'<a href="{DETAIL}">Administration Assistant</a>',
        UNOPS_SITE,
    ).jobs[0]
    job = apply_detail(listed, html)
    assert job.closes_at == datetime(2026, 10, 12, 23, 59, 59, tzinfo=UTC)
    assert job.note == ZONE_NOTE


def test_the_same_id_with_another_slug_does_not_duplicate(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    slugs = iter(("Administration-Assistant", "Admin-Assistant"))

    def fetch(url: str) -> tuple[int, str, str]:
        slug = next(slugs)
        html = (
            "<p>1-1 of 1 results</p>"
            f'<a href="/careersmarketplace/JobDetail/{slug}/4611">Administration Assistant</a>'
        )
        return 200, html, url

    monkeypatch.setattr("jobbot.adapters.avature.discover.fetch_public", fetch)
    monkeypatch.setattr("jobbot.adapters.avature.discover.pause", lambda: None)
    assert run_cli(
        ["jobs", "discover", "--source", "unops", "--query", "health", "--limit", "5"],
        standalone_mode=False,
    ) == 0
    assert run_cli(
        ["jobs", "discover", "--source", "unops", "--query", "health", "--limit", "5"],
        standalone_mode=False,
    ) == 0
    stored = list((tmp_path / "output" / "jobs").glob("*/job.json"))
    assert len(stored) == 1


def test_companies_learn_keeps_the_redirected_avature_site(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    final = "https://careers.unops.org/careersmarketplace"
    monkeypatch.setattr(
        "jobbot.companies.discovery.follow_redirect_url",
        lambda _url: final,
    )
    fixture = project_root / FIXTURES / "marketplace.html"
    code = run_cli(
        [
            "companies",
            "learn",
            "https://jobs.unops.org/Pages/ViewVacancy/VAListing.aspx",
            "--company",
            "Ejemplo",
            "--resolve",
            "--fixture",
            str(fixture),
        ],
        standalone_mode=False,
    )
    assert code == 0
    saved = yaml.safe_load((tmp_path / "data" / "companies.yaml").read_text(encoding="utf-8"))
    site = saved["companies"][0]["career_sites"][0]
    assert site["ats"] == "avature"
    assert "careers.unops.org" in site["url"]


def test_a_qtvc_link_is_not_requested(project_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    robots = (project_root / FIXTURES / "robots.txt").read_text(encoding="utf-8")
    assert "Disallow: /careersmarketplace/*qtvc=" in robots
    calls: list[str] = []

    def fetch(url: str) -> tuple[int, str, str]:
        calls.append(url)
        if "SearchJobs" in url:
            html = (
                "<p>1-1 of 1 results</p>"
                f'<a href="{DETAIL}?qtvc=session">Administration Assistant</a>'
            )
            return 200, html, url
        return 200, "<p>Position Title Administration Assistant</p>", url

    monkeypatch.setattr("jobbot.adapters.avature.discover.fetch_public", fetch)
    monkeypatch.setattr("jobbot.adapters.avature.discover.pause", lambda: None)
    outcome = AvatureDiscover().discover_site(
        SiteTarget(url=UNOPS_SITE),
        query="health",
        limit=5,
        details=True,
    )
    assert outcome.status is SiteStatus.OK
    assert all(not blocked_qtvc(url) for url in calls)
    assert any(url.rstrip("/") == DETAIL for url in calls)


def test_a_list_without_results_exits_changed(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    html = (project_root / FIXTURES / "search_changed.html").read_text(encoding="utf-8")
    monkeypatch.setattr(
        "jobbot.adapters.avature.discover.fetch_public",
        lambda url: (200, html, url),
    )
    monkeypatch.setattr("jobbot.adapters.avature.discover.pause", lambda: None)
    code = run_cli(
        ["jobs", "discover", "--source", "unops", "--query", "health", "--dry-run"],
        standalone_mode=False,
    )
    assert code == 5


def test_avature_host_and_widget(project_root: Path) -> None:
    assert detect_ats("https://jobs.avature.net/portal") is AtsKind.AVATURE
    html = (project_root / FIXTURES / "marketplace.html").read_text(encoding="utf-8")
    kind, evidence = detect_ats_in_html(html)
    assert kind is AtsKind.AVATURE
    assert "avature" in evidence


def test_a_site_without_a_portal_path_is_rejected() -> None:
    with pytest.raises(ValueError, match="portal"):
        AvatureDiscover().site_target("careers.ejemplo.cl")


def test_apply_detail_accepts_a_posting() -> None:
    job = JobPosting(id="pending", title="Role", company="unops", source="avature")
    updated = apply_detail(job, "<p>Duty Station(s) Home-based</p>")
    assert updated.remote_type == "remote"
