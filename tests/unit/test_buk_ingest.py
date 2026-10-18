"""Buk is recognised, refused by robots.txt, and ingested from saved HTML."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from jobbot.cli import run_cli
from jobbot.companies.oneshot import FetchResult
from jobbot.portals.detect import AtsKind, detect_ats

FIXTURES = Path("tests/fixtures/buk")
LIST_URL = "https://acme.buk.cl/trabaja-con-nosotros"


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


def test_buk_host_is_detected() -> None:
    assert detect_ats(LIST_URL) is AtsKind.BUK
    assert detect_ats("https://acme.buk.mx/careers") is AtsKind.BUK


def test_discover_reads_only_robots_and_refuses(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    calls: list[str] = []
    robots = (project_root / FIXTURES / "robots.txt").read_text(encoding="utf-8")

    def fake_robots(url: str) -> str:
        calls.append(url)
        return robots

    monkeypatch.setattr("jobbot.adapters.buk.discover.fetch_robots", fake_robots)
    code = run_cli(
        ["jobs", "discover", "--source", "buk", "--site", LIST_URL],
        standalone_mode=False,
    )
    captured = capsys.readouterr()
    assert code == 1
    assert calls == ["https://acme.buk.cl/robots.txt"]
    assert "blocked (robots)" in captured.out
    assert "jobs add --file" in captured.out


def test_companies_discover_records_a_blocked_buk_portal(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    seeds = tmp_path / "seeds.yaml"
    seeds.write_text("companies:\n  - name: Acme\n    id: acme\n", encoding="utf-8")
    robots = (project_root / FIXTURES / "robots.txt").read_text(encoding="utf-8")
    page = (project_root / FIXTURES / "listado.html").read_text(encoding="utf-8")

    class FakeFetcher:
        def __init__(self, delay: float = 0.0) -> None:
            self.delay = delay

        def fetch(self, url: str) -> FetchResult:
            if url.endswith("/robots.txt"):
                return FetchResult(url=url, status=200, html=robots)
            if url.endswith("/trabaja-con-nosotros"):
                return FetchResult(url=url, status=200, html=page)
            return FetchResult(url=url, status=404)

    monkeypatch.setattr("jobbot.companies.oneshot.UrllibFetcher", FakeFetcher)
    out = tmp_path / "candidates.yaml"
    code = run_cli(
        ["companies", "discover", str(seeds), "--out", str(out)],
        standalone_mode=False,
    )
    assert code == 0
    text = out.read_text(encoding="utf-8")
    assert "ats: buk" in text
    assert "discovery: blocked (robots)" in text
    assert "prohibe agentes genericos" in text or "prohíbe agentes genéricos" in text


def test_saved_list_creates_three_postings(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    listing = project_root / FIXTURES / "listado.html"
    code = run_cli(
        ["jobs", "add", "--file", str(listing), "--url", LIST_URL],
        standalone_mode=False,
    )
    assert code == 0
    jobs = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted((tmp_path / "output" / "jobs").glob("*/job.json"))
    ]
    assert len(jobs) == 3
    assert {job["source_job_id"] for job in jobs} == {"acme:a1b2", "acme:c3d4", "acme:e5f6"}
    assert {job["url"] for job in jobs} == {
        "https://acme.buk.cl/s/a1b2",
        "https://acme.buk.cl/s/c3d4",
        "https://acme.buk.cl/s/e5f6",
    }
    assert {job["title"] for job in jobs} == {
        "Turno de manana",
        "Apoyo en terreno",
        "Registro de sala",
    }


def test_list_without_cards_exits_ui_changed(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    empty = project_root / FIXTURES / "listado_sin_tarjetas.html"
    code = run_cli(
        ["jobs", "add", "--file", str(empty), "--url", LIST_URL],
        standalone_mode=False,
    )
    captured = capsys.readouterr()
    assert code == 5
    assert "jobs__card" in captured.err
