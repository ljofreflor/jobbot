"""Greenhouse Job Board API: deadline, HTML, known jobs, partial 404. No network."""

from __future__ import annotations

import json
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from jobbot.adapters.greenhouse.parse import job_from_item, public_job_url
from jobbot.cli import run_cli

FIXTURES = Path("tests/fixtures/greenhouse")
POSTED = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
CLOSES = datetime(2026, 12, 1, 23, 59, 59, tzinfo=UTC)


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
    monkeypatch.setattr("jobbot.adapters.greenhouse.discover.fetch_public", fetch)
    monkeypatch.setattr("jobbot.adapters.greenhouse.discover.pause", lambda: None)


def _companies(tmp_path: Path) -> None:
    payload = {
        "version": 1,
        "companies": [
            {
                "id": "acme",
                "name": "Acme",
                "career_sites": [
                    {
                        "url": "https://job-boards.greenhouse.io/acme",
                        "domain": "job-boards.greenhouse.io",
                        "site_type": "ats_instance",
                        "ats": "greenhouse",
                        "status": "active",
                    }
                ],
            },
            {
                "id": "norte",
                "name": "Norte",
                "career_sites": [
                    {
                        "url": "https://job-boards.greenhouse.io/norte",
                        "domain": "job-boards.greenhouse.io",
                        "site_type": "ats_instance",
                        "ats": "greenhouse",
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


def test_dry_run_lists_the_board_and_writes_nothing(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    _companies(tmp_path)
    page = json.loads((project_root / FIXTURES / "board_jobs.json").read_text(encoding="utf-8"))
    mapped = job_from_item(page["jobs"][0], "acme")
    assert mapped is not None
    assert mapped.posted_at == POSTED
    assert mapped.closes_at == CLOSES
    assert mapped.url == "https://careers.acme-demo.cl/jobs/1?gh_jid=123"
    assert "utm_source" not in (mapped.url or "")
    assert mapped.description == "Hola equipo"
    assert mapped.raw_description == "<p>Hola equipo</p>"
    assert mapped.remote_type is None
    remote = job_from_item(page["jobs"][1], "acme")
    assert remote is not None and remote.remote_type == "remote"
    calls: list[str] = []

    def fetch(url: str) -> tuple[int, str, str]:
        calls.append(url)
        if "norte" in url:
            return 200, json.dumps({"jobs": [], "meta": {"total": 0}}), url
        return 200, json.dumps(page), url

    _install(monkeypatch, fetch)
    code = run_cli(
        ["jobs", "discover", "--source", "greenhouse", "--dry-run"],
        standalone_mode=False,
    )
    captured = capsys.readouterr()
    assert code == 0
    assert any("content=true" in url for url in calls)
    assert all("/embed/" not in url for url in calls)
    assert "Program lead" in captured.out
    assert "Acme" in captured.out
    assert "Santiago, Chile" in captured.out
    assert "Nothing written." in captured.out
    assert list((tmp_path / "output" / "jobs").glob("*/job.json")) == []


def test_an_expired_deadline_is_not_stored(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    page = (project_root / FIXTURES / "board_jobs.json").read_text(encoding="utf-8")

    def fetch(url: str) -> tuple[int, str, str]:
        return 200, page, url

    _install(monkeypatch, fetch)
    code = run_cli(
        ["jobs", "discover", "--source", "greenhouse", "--board", "acme"],
        standalone_mode=False,
    )
    assert code == 0
    stored = list((tmp_path / "output" / "jobs").glob("*/job.json"))
    assert len(stored) == 1
    saved = json.loads(stored[0].read_text(encoding="utf-8"))
    assert saved["source_job_id"] == "acme:1"


def test_a_known_job_skips_content_and_detail(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    full = (project_root / FIXTURES / "board_jobs.json").read_text(encoding="utf-8")
    bare = (project_root / FIXTURES / "board_jobs_nocontent.json").read_text(encoding="utf-8")
    calls: list[str] = []

    def fetch(url: str) -> tuple[int, str, str]:
        calls.append(url)
        if "/jobs/" in url.split("?", 1)[0]:
            raise AssertionError(url)
        if "content=false" in url:
            return 200, bare, url
        return 200, full, url

    _install(monkeypatch, fetch)
    args = ["jobs", "discover", "--source", "greenhouse", "--board", "acme"]
    assert run_cli(args, standalone_mode=False) == 0
    assert run_cli(args, standalone_mode=False) == 0
    assert any("content=true" in url for url in calls)
    assert any("content=false" in url for url in calls)
    assert list((tmp_path / "output" / "jobs").glob("*/job.json"))


def test_a_404_does_not_drop_the_other_board(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    _companies(tmp_path)
    page = (project_root / FIXTURES / "board_jobs.json").read_text(encoding="utf-8")

    def fetch(url: str) -> tuple[int, str, str]:
        if "/acme/" in url:
            missing = (project_root / FIXTURES / "board_404.json").read_text(encoding="utf-8")
            return 404, missing, url
        return 200, page, url

    _install(monkeypatch, fetch)
    code = run_cli(
        ["jobs", "discover", "--source", "greenhouse"],
        standalone_mode=False,
    )
    assert code == 0
    stored = list((tmp_path / "output" / "jobs").glob("*/job.json"))
    assert len(stored) == 1
    saved = json.loads(stored[0].read_text(encoding="utf-8"))
    assert saved["source_job_id"] == "norte:1"


def test_tracking_parameters_drop_and_gh_jid_stays() -> None:
    url = public_job_url("https://careers.acme-demo.cl/jobs/1?gh_jid=123&utm_source=x")
    assert url == "https://careers.acme-demo.cl/jobs/1?gh_jid=123"


def test_a_board_without_jobs_exits_5(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    page = (project_root / FIXTURES / "board_shape_changed.json").read_text(encoding="utf-8")

    def fetch(url: str) -> tuple[int, str, str]:
        return 200, page, url

    _install(monkeypatch, fetch)
    code = run_cli(
        ["jobs", "discover", "--source", "greenhouse", "--board", "acme", "--dry-run"],
        standalone_mode=False,
    )
    assert code == 5


def test_a_bad_board_token_exits_2(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("socket")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    code = run_cli(
        ["jobs", "discover", "--source", "greenhouse", "--board", "acme/jobs"],
        standalone_mode=False,
    )
    assert code == 2
