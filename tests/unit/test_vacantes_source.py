"""Vacantes.com landings and JSON-LD. No network, no /api/, no query string."""

from __future__ import annotations

import urllib.request
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

import pytest
import yaml

from jobbot.adapters.vacantes.parse import job_from_html
from jobbot.cli import run_cli

FIXTURES = Path("tests/fixtures/vacantes")
ROOT = "https://vacantes.com"
ROBOTS = f"{ROOT}/robots.txt"
LANDING = f"{ROOT}/es/empleo/empleos-en-chile/"
SITEMAP = f"{ROOT}/sitemap.xml"
VACANCIES = f"{ROOT}/sitemap-vacancies.xml"


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


def _text(project_root: Path, name: str) -> str:
    return (project_root / FIXTURES / name).read_text(encoding="utf-8")


def _install(monkeypatch: pytest.MonkeyPatch, fetch: object) -> None:
    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("socket")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    monkeypatch.setattr("jobbot.adapters.vacantes.discover.fetch_public", fetch)
    monkeypatch.setattr("jobbot.adapters.vacantes.discover.pause", lambda: None)


def _detail(project_root: Path, title: str, identifier: str, slug: str) -> str:
    return (
        _text(project_root, "detail_jsonld.html")
        .replace("Health advisor", title)
        .replace("11111111-1111-4111-8111-111111111111", identifier)
        .replace("health-advisor-aaa11111", slug)
    )


def test_jsonld_keeps_close_salary_and_place(project_root: Path) -> None:
    job = job_from_html(
        _text(project_root, "detail_jsonld.html"),
        page_url=f"{ROOT}/es/vacantes/health-advisor-aaa11111/",
    )
    assert job is not None
    assert job.title == "Health advisor"
    assert job.company == "Organizacion Ejemplo"
    assert job.location == "Santiago, Region Metropolitana, Chile"
    assert job.posted_at == datetime.fromisoformat("2026-10-06T09:00:00-03:00")
    assert job.closes_at == datetime.fromisoformat("2026-12-22T18:00:00-03:00")
    assert job.note == "1200000 CLP"
    assert job.source_job_id == "11111111-1111-4111-8111-111111111111"
    assert job.url is not None and job.url.endswith("/")
    assert "?" not in job.url


def test_dry_run_lists_three_and_writes_nothing(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    calls: list[str] = []
    details = {
        "aaa11111": _detail(
            project_root,
            "Health advisor",
            "11111111-1111-4111-8111-111111111111",
            "health-advisor-aaa11111",
        ),
        "bbb22222": _detail(
            project_root,
            "Data advisor",
            "22222222-2222-4222-8222-222222222222",
            "data-advisor-bbb22222",
        ),
        "ccc33333": _detail(
            project_root,
            "Program lead",
            "33333333-3333-4333-8333-333333333333",
            "program-lead-ccc33333",
        ),
    }

    def fetch(url: str) -> tuple[int, str]:
        calls.append(url)
        assert "?" not in url
        assert "/api/" not in url
        if url == ROBOTS:
            return 200, _text(project_root, "robots.txt")
        if url == LANDING:
            return 200, _text(project_root, "landing_chile.html")
        for hex_id, body in details.items():
            if hex_id in url:
                return 200, body
        raise AssertionError(url)

    _install(monkeypatch, fetch)
    code = run_cli(
        [
            "jobs",
            "discover",
            "--source",
            "vacantes",
            "--country",
            "CL",
            "--query",
            "health",
            "--dry-run",
        ],
        standalone_mode=False,
    )
    out = capsys.readouterr().out
    assert code == 0
    assert "Health advisor" in out
    assert "Data advisor" in out
    assert "Program lead" in out
    assert "Organizacion Ejemplo" in out
    assert "Santiago" in out
    assert "2026-12-22" in out
    assert "Nothing written." in out
    assert list(tmp_path.glob("output/jobs/*/job.json")) == []
    assert calls[0] == ROBOTS
    assert all("?" not in url and "/api/" not in url for url in calls)


def test_all_sitemap_requests_only_matching_slugs(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    calls: list[str] = []
    detail = _text(project_root, "detail_jsonld.html")

    def fetch(url: str) -> tuple[int, str]:
        calls.append(url)
        assert "?" not in url and "/api/" not in url
        if url == ROBOTS:
            return 200, _text(project_root, "robots.txt")
        if url == SITEMAP:
            return 200, _text(project_root, "sitemap_index.xml")
        if url == VACANCIES:
            return 200, _text(project_root, "sitemap_vacancies.xml")
        if "salud" in url:
            return 200, detail
        raise AssertionError(url)

    _install(monkeypatch, fetch)
    code = run_cli(
        [
            "jobs",
            "discover",
            "--source",
            "vacantes",
            "--country",
            "CL",
            "--all-sitemap",
            "--query",
            "salud",
            "--dry-run",
        ],
        standalone_mode=False,
    )
    assert code == 0
    detail_calls = [url for url in calls if "/es/vacantes/" in url]
    assert len(detail_calls) == 2
    assert all("salud" in url for url in detail_calls)
    assert LANDING not in calls
    assert "cargo-uno" not in " ".join(calls)
    capsys.readouterr()


def test_expired_posting_is_not_stored(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)

    def fetch(url: str) -> tuple[int, str]:
        if url == ROBOTS:
            return 200, _text(project_root, "robots.txt")
        if url == LANDING:
            return 200, _text(project_root, "landing_chile.html")
        return 200, _text(project_root, "detail_expired.html")

    _install(monkeypatch, fetch)
    code = run_cli(
        ["jobs", "discover", "--source", "vacantes", "--country", "CL", "--query", "health"],
        standalone_mode=False,
    )
    assert code == 0
    assert list(tmp_path.glob("output/jobs/*/job.json")) == []
    capsys.readouterr()


def test_known_uuid_is_not_fetched_again(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    calls: list[str] = []
    details = {
        "aaa11111": _detail(
            project_root,
            "Health advisor",
            "11111111-1111-4111-8111-111111111111",
            "health-advisor-aaa11111",
        ),
        "bbb22222": _detail(
            project_root,
            "Data advisor",
            "22222222-2222-4222-8222-222222222222",
            "data-advisor-bbb22222",
        ),
        "ccc33333": _detail(
            project_root,
            "Program lead",
            "33333333-3333-4333-8333-333333333333",
            "program-lead-ccc33333",
        ),
    }

    def fetch(url: str) -> tuple[int, str]:
        calls.append(url)
        if url == ROBOTS:
            return 200, _text(project_root, "robots.txt")
        if url == LANDING:
            return 200, _text(project_root, "landing_chile.html")
        for hex_id, body in details.items():
            if hex_id in url:
                return 200, body
        raise AssertionError(url)

    _install(monkeypatch, fetch)
    argv = ["jobs", "discover", "--source", "vacantes", "--country", "CL", "--query", "health"]
    assert run_cli(argv, standalone_mode=False) == 0
    stored = list(tmp_path.glob("output/jobs/*/job.json"))
    assert len(stored) == 3
    calls.clear()
    assert run_cli(argv, standalone_mode=False) == 0
    assert list(tmp_path.glob("output/jobs/*/job.json")) == stored
    assert not any("/es/vacantes/" in url for url in calls)
    capsys.readouterr()


def test_landing_is_read_once_without_query(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    calls: list[str] = []

    def fetch(url: str) -> tuple[int, str]:
        calls.append(url)
        if url == ROBOTS:
            return 200, _text(project_root, "robots.txt")
        if url == LANDING:
            return 200, _text(project_root, "landing_chile.html")
        return 200, _text(project_root, "detail_jsonld.html")

    _install(monkeypatch, fetch)
    code = run_cli(
        ["jobs", "discover", "--source", "vacantes", "--country", "CL", "--dry-run"],
        standalone_mode=False,
    )
    assert code == 0
    assert calls.count(LANDING) == 1
    capsys.readouterr()


def test_robots_disallow_on_vacancies_stops_before_any_detail(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    calls: list[str] = []

    def fetch(url: str) -> tuple[int, str]:
        calls.append(url)
        if url == ROBOTS:
            return 200, "User-agent: *\nDisallow: /es/vacantes/\n"
        raise AssertionError(url)

    _install(monkeypatch, fetch)
    code = run_cli(
        ["jobs", "discover", "--source", "vacantes", "--country", "CL", "--query", "health"],
        standalone_mode=False,
    )
    captured = capsys.readouterr()
    assert code == 1
    assert calls == [ROBOTS]
    assert "robots.txt disallows /es/vacantes/" in captured.out


def test_sitemap_does_not_refetch_a_stored_vacancy(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    calls: list[str] = []

    def fetch(url: str) -> tuple[int, str]:
        calls.append(url)
        if url == ROBOTS:
            return 200, _text(project_root, "robots.txt")
        if url == LANDING:
            return 200, _text(project_root, "landing_chile.html")
        if url == SITEMAP:
            return 200, _text(project_root, "sitemap_index.xml")
        if url == VACANCIES:
            return 200, _text(project_root, "sitemap_vacancies.xml")
        slug = urlsplit(url).path.strip("/").rsplit("/", 1)[-1]
        hex_id = slug[-8:]
        return 200, _detail(project_root, f"Cargo {hex_id}", f"{hex_id}-uuid", slug)

    _install(monkeypatch, fetch)
    landing = ["jobs", "discover", "--source", "vacantes", "--country", "CL", "--query", "health"]
    assert run_cli(landing, standalone_mode=False) == 0
    calls.clear()
    sitemap = [*landing[:-1], "cargo", "--all-sitemap"]
    assert run_cli(sitemap, standalone_mode=False) == 0
    assert not any("ccc33333" in url for url in calls)
    assert any("ddd44444" in url for url in calls)
    capsys.readouterr()


def test_unknown_country_exits_2(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)

    def fetch(url: str) -> tuple[int, str]:
        raise AssertionError(url)

    _install(monkeypatch, fetch)
    code = run_cli(
        ["jobs", "discover", "--source", "vacantes", "--country", "XX", "--query", "health"],
        standalone_mode=False,
    )
    err = capsys.readouterr().err
    assert code == 2
    assert "Available: CL" in err


def test_robots_disallow_does_not_fetch_the_landing(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    calls: list[str] = []

    def fetch(url: str) -> tuple[int, str]:
        calls.append(url)
        if url == ROBOTS:
            return 200, _text(project_root, "robots_disallow_empleo.txt")
        raise AssertionError(url)

    _install(monkeypatch, fetch)
    code = run_cli(
        ["jobs", "discover", "--source", "vacantes", "--country", "CL", "--query", "health"],
        standalone_mode=False,
    )
    captured = capsys.readouterr()
    assert code == 1
    assert calls == [ROBOTS]
    assert "robots.txt disallows" in captured.out
    assert "jobs add --file" in captured.out


def test_detail_without_jsonld_exits_5(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)

    def fetch(url: str) -> tuple[int, str]:
        if url == ROBOTS:
            return 200, _text(project_root, "robots.txt")
        if url == LANDING:
            return 200, _text(project_root, "landing_chile.html")
        return 200, _text(project_root, "detail_no_jsonld.html")

    _install(monkeypatch, fetch)
    code = run_cli(
        [
            "jobs",
            "discover",
            "--source",
            "vacantes",
            "--country",
            "CL",
            "--query",
            "health",
            "--dry-run",
        ],
        standalone_mode=False,
    )
    assert code == 5
    assert "JSON-LD" in capsys.readouterr().out
