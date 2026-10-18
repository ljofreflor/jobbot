"""Poder Judicial contest grid: closing zone, local filter, no login. No network."""

from __future__ import annotations

import json
import urllib.request
from datetime import datetime
from html import escape
from pathlib import Path

import pytest
import yaml

from jobbot.adapters.pjud.parse import LISTING, SANTIAGO, parse_grid
from jobbot.cli import run_cli

FIXTURES = Path("tests/fixtures/pjud")


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
    monkeypatch.setattr("jobbot.adapters.pjud.discover.fetch_public", fetch)
    monkeypatch.setattr("jobbot.adapters.pjud.discover.pause", lambda: None)


def test_dry_run_lists_ten_and_writes_nothing(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    page = (project_root / FIXTURES / "concursos_en_postulacion.html").read_text(encoding="utf-8")
    calls: list[str] = []

    def fetch(url: str) -> tuple[int, str, str]:
        calls.append(url)
        return 200, page, url

    _install(monkeypatch, fetch)
    code = run_cli(["jobs", "discover", "--source", "pjud", "--dry-run"], standalone_mode=False)
    captured = capsys.readouterr()
    assert code == 0
    assert calls == [LISTING]
    assert all("postulacionessrh" not in url for url in calls)
    assert "10 avisos" in captured.out
    assert "JUEZ (24841)" in captured.out
    assert "Corte de Santiago" in captured.out
    assert "Santiago, Chile" in captured.out
    assert "2026-10-12 23:59" in captured.out
    assert "Nothing written." in captured.out
    assert list((tmp_path / "output" / "jobs").glob("*/job.json")) == []


def test_close_is_end_of_day_in_santiago(project_root: Path) -> None:
    html = (project_root / FIXTURES / "concursos_en_postulacion.html").read_text(encoding="utf-8")
    job = parse_grid(html).jobs[0]
    assert job.closes_at == datetime(2026, 10, 12, 23, 59, 59, tzinfo=SANTIAGO)
    assert job.posted_at == datetime(2026, 10, 2, 0, 0, tzinfo=SANTIAGO)
    assert job.note is not None
    assert "hora no publicada" in job.note
    assert job.source_job_id == "24841"
    assert job.url == f"{LISTING}#concurso-24841"


def test_a_primary_ladder_is_marked_in_the_preview(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    html = (project_root / FIXTURES / "concursos_en_postulacion.html").read_text(encoding="utf-8")
    judge = next(job for job in parse_grid(html).jobs if job.source_job_id == "24841")
    assert judge.seniority == "PR10"
    assert judge.note is not None
    assert "escalafón primario" in judge.note
    _workspace(tmp_path, project_root, monkeypatch)

    def fetch(url: str) -> tuple[int, str, str]:
        return 200, html, url

    _install(monkeypatch, fetch)
    code = run_cli(["jobs", "discover", "--source", "pjud", "--dry-run"], standalone_mode=False)
    assert code == 0
    assert "PR10" in capsys.readouterr().out


def test_query_keeps_only_matching_titles(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    page = (project_root / FIXTURES / "concursos_en_postulacion.html").read_text(encoding="utf-8")

    def fetch(url: str) -> tuple[int, str, str]:
        return 200, page, url

    _install(monkeypatch, fetch)
    code = run_cli(
        ["jobs", "discover", "--source", "pjud", "--query", "receptor", "--dry-run"],
        standalone_mode=False,
    )
    captured = capsys.readouterr()
    assert code == 0
    assert "2 avisos" in captured.out
    assert "RECEPTOR JUDICIAL" in captured.out
    assert "JUEZ" not in captured.out


def test_a_short_row_exits_5(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    page = (project_root / FIXTURES / "grid_changed.html").read_text(encoding="utf-8")

    def fetch(url: str) -> tuple[int, str, str]:
        return 200, page, url

    _install(monkeypatch, fetch)
    code = run_cli(["jobs", "discover", "--source", "pjud", "--dry-run"], standalone_mode=False)
    assert code == 5


def test_the_same_contest_number_does_not_duplicate(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    cells = [""] * 29
    cells[0] = "POSTULAR"
    cells[1] = "SSSF"
    cells[6] = "30001"
    cells[9] = "SECRETARIO"
    cells[10] = "Santiago"
    cells[11] = "Corte de Santiago"
    cells[12] = "02/10/2026"
    cells[13] = "12/12/2026"
    cells[15] = "Poder Judicial"
    payload = json.dumps([cells], ensure_ascii=False)
    html = (
        "<html><body><form>"
        f'<input type="hidden" name="GridContainerDataV" value="{escape(payload, quote=True)}">'
        "</form></body></html>"
    )
    calls: list[str] = []

    def fetch(url: str) -> tuple[int, str, str]:
        calls.append(url)
        return 200, html, url

    _install(monkeypatch, fetch)
    args = ["jobs", "discover", "--source", "pjud", "--query", "secretario"]
    assert run_cli(args, standalone_mode=False) == 0
    assert run_cli(args, standalone_mode=False) == 0
    stored = list((tmp_path / "output" / "jobs").glob("*/job.json"))
    assert len(stored) == 1
    assert all("postulacionessrh" not in url for url in calls)
