"""SmartRecruiters Posting API: country filter, offset pages, partial 404. No network."""

from __future__ import annotations

import json
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from jobbot.adapters.smartrecruiters.parse import parse_postings
from jobbot.cli import run_cli

FIXTURES = Path("tests/fixtures/smartrecruiters")
RELEASED = datetime(2026, 10, 8, 15, 0, tzinfo=UTC)


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
    monkeypatch.setattr("jobbot.adapters.smartrecruiters.discover.fetch_public", fetch)
    monkeypatch.setattr("jobbot.adapters.smartrecruiters.discover.pause", lambda: None)


def _companies(tmp_path: Path) -> None:
    payload = {
        "version": 1,
        "companies": [
            {
                "id": "norte",
                "name": "Norte",
                "career_sites": [
                    {
                        "url": "https://jobs.smartrecruiters.com/NorteDemo",
                        "domain": "jobs.smartrecruiters.com",
                        "site_type": "ats_instance",
                        "ats": "smartrecruiters",
                        "status": "active",
                    }
                ],
            },
            {
                "id": "sur",
                "name": "Sur",
                "career_sites": [
                    {
                        "url": "https://jobs.smartrecruiters.com/SurDemo",
                        "domain": "jobs.smartrecruiters.com",
                        "site_type": "ats_instance",
                        "ats": "smartrecruiters",
                        "status": "active",
                    }
                ],
            },
        ],
    }
    (tmp_path / "data" / "companies.yaml").write_text(
        yaml.safe_dump(payload, allow_unicode=True),
        encoding="utf-8",
    )


def test_dry_run_shows_the_chile_posting_and_writes_nothing(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    page = (project_root / FIXTURES / "postings_cl.json").read_text(encoding="utf-8")
    mapped = parse_postings(json.loads(page), "AcmeCorp")
    assert mapped is not None
    job = mapped[0][0]
    assert job.posted_at == RELEASED
    assert job.url == "https://jobs.smartrecruiters.com/AcmeCorp/12345"
    assert job.closes_at is None
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
            "smartrecruiters",
            "--company",
            "AcmeCorp",
            "--query",
            "legal",
            "--dry-run",
        ],
        standalone_mode=False,
    )
    captured = capsys.readouterr()
    assert code == 0
    assert calls and "q=legal" in calls[0] and "country=cl" in calls[0]
    assert "Counsel" in captured.out
    assert "Santiago" in captured.out
    assert "Chile" in captured.out
    assert "Nothing written." in captured.out
    assert list((tmp_path / "output" / "jobs").glob("*/job.json")) == []


def test_a_foreign_posting_is_dropped(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    page = (project_root / FIXTURES / "postings_mixed_countries.json").read_text(encoding="utf-8")

    def fetch(url: str) -> tuple[int, str, str]:
        return 200, page, url

    _install(monkeypatch, fetch)
    code = run_cli(
        [
            "jobs",
            "discover",
            "--source",
            "smartrecruiters",
            "--company",
            "AcmeCorp",
            "--country",
            "CL",
            "--query",
            "legal",
            "--dry-run",
        ],
        standalone_mode=False,
    )
    captured = capsys.readouterr()
    assert code == 0
    assert "1 avisos" in captured.out
    assert "Santiago" in captured.out
    assert "Madrid" not in captured.out


def test_three_offsets_cover_two_hundred_fifty(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    root = project_root / FIXTURES
    pages = {
        "offset=0": (root / "postings_page1.json").read_text(encoding="utf-8"),
        "offset=100": (root / "postings_page2.json").read_text(encoding="utf-8"),
        "offset=200": (root / "postings_page3.json").read_text(encoding="utf-8"),
    }
    calls: list[str] = []

    def fetch(url: str) -> tuple[int, str, str]:
        calls.append(url)
        for key, body in pages.items():
            if key in url:
                return 200, body, url
        raise AssertionError(url)

    _install(monkeypatch, fetch)
    code = run_cli(
        [
            "jobs",
            "discover",
            "--source",
            "smartrecruiters",
            "--company",
            "AcmeCorp",
            "--query",
            "legal",
            "--limit",
            "250",
            "--dry-run",
        ],
        standalone_mode=False,
    )
    assert code == 0
    assert any("offset=0&" in url for url in calls)
    assert any("offset=100&" in url for url in calls)
    assert any("offset=200&" in url for url in calls)
    assert not any("offset=300" in url for url in calls)


def test_registry_boards_are_both_queried(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    _companies(tmp_path)
    page = (project_root / FIXTURES / "postings_cl.json").read_text(encoding="utf-8")
    calls: list[str] = []

    def fetch(url: str) -> tuple[int, str, str]:
        calls.append(url)
        return 200, page, url

    _install(monkeypatch, fetch)
    code = run_cli(
        ["jobs", "discover", "--source", "smartrecruiters", "--query", "legal", "--dry-run"],
        standalone_mode=False,
    )
    assert code == 0
    assert any("/NorteDemo/" in url for url in calls)
    assert any("/SurDemo/" in url for url in calls)


def test_a_404_does_not_drop_the_other_board(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    _companies(tmp_path)
    page = (project_root / FIXTURES / "postings_cl.json").read_text(encoding="utf-8")

    def fetch(url: str) -> tuple[int, str, str]:
        if "NorteDemo" in url:
            return 404, "{}", url
        return 200, page, url

    _install(monkeypatch, fetch)
    code = run_cli(
        ["jobs", "discover", "--source", "smartrecruiters", "--query", "legal"],
        standalone_mode=False,
    )
    assert code == 0
    stored = list((tmp_path / "output" / "jobs").glob("*/job.json"))
    assert len(stored) == 1
    saved = json.loads(stored[0].read_text(encoding="utf-8"))
    assert saved["source_job_id"] == "SurDemo:12345"


def test_the_same_posting_id_does_not_duplicate(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    page = (project_root / FIXTURES / "postings_cl.json").read_text(encoding="utf-8")

    def fetch(url: str) -> tuple[int, str, str]:
        return 200, page, url

    _install(monkeypatch, fetch)
    args = [
        "jobs",
        "discover",
        "--source",
        "smartrecruiters",
        "--company",
        "AcmeCorp",
        "--query",
        "legal",
    ]
    assert run_cli(args, standalone_mode=False) == 0
    assert run_cli(args, standalone_mode=False) == 0
    stored = list((tmp_path / "output" / "jobs").glob("*/job.json"))
    assert len(stored) == 1


def test_a_changed_shape_exits_5(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    page = (project_root / FIXTURES / "postings_shape_changed.json").read_text(encoding="utf-8")

    def fetch(url: str) -> tuple[int, str, str]:
        return 200, page, url

    _install(monkeypatch, fetch)
    code = run_cli(
        [
            "jobs",
            "discover",
            "--source",
            "smartrecruiters",
            "--company",
            "AcmeCorp",
            "--query",
            "legal",
            "--dry-run",
        ],
        standalone_mode=False,
    )
    assert code == 5


def test_an_unknown_country_exits_2(
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
            "smartrecruiters",
            "--company",
            "AcmeCorp",
            "--country",
            "not-a-country",
            "--query",
            "legal",
        ],
        standalone_mode=False,
    )
    assert code == 2
