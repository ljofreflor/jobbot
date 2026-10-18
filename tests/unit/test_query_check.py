"""profile queries --check scores titles and stores nothing (issue #260)."""

from __future__ import annotations

import socket
from pathlib import Path

import pytest
import yaml
from sqlalchemy import func, select

from jobbot.exit_codes import SUCCESS, VALIDATION_FAILURE
from jobbot.models.candidate import Candidate
from jobbot.profile.query_check import (
    EMPTY_SUGGESTION,
    NOISE_SUGGESTION,
    QueryCheck,
    measure_queries,
    significant_stems,
    title_covers,
)


def _candidate() -> Candidate:
    return Candidate.model_validate(
        {
            "personal": {"name": "Ana Ejemplo", "headline": "Analista"},
            "experience": [
                {
                    "id": "e1",
                    "company": "Acme",
                    "title": "Analista",
                    "start_date": "2020-01",
                    "end_date": "2024-01",
                    "description": "Informes mensuales para el equipo",
                }
            ],
        }
    )


def _codes(report: QueryCheck) -> set[str]:
    return {warning.code for warning in report.warnings}


def test_title_match_ignores_accent_and_gender() -> None:
    assert title_covers("geofísico", "Geofísica de terreno")
    assert significant_stems("proyectos") == significant_stems("proyecto")


def test_no_title_holds_every_root() -> None:
    report = measure_queries(
        _candidate(),
        ["Médico veterinario salud pública"],
        ["demo"],
        lambda _source, _query: [
            "Médico Veterinario Inspector",
            "Profesional Salud Pública",
        ],
    )
    cell = report.cells[0]
    assert cell.returned == 2
    assert cell.title_matches == 0
    assert _codes(report) == {"sin calce"}
    assert report.warnings[0].suggestion.startswith("Dividir: probar ")
    for stem in significant_stems("Médico veterinario salud pública"):
        assert f'"{stem}"' in report.warnings[0].suggestion


def test_foreign_dominant_words_are_ambiguous() -> None:
    titles = [f"Referente de vigilancia guardia seguridad {n}" for n in range(6)]
    report = measure_queries(
        _candidate(),
        ["Referente de vigilancia"],
        ["demo"],
        lambda _source, _query: titles,
    )
    cell = report.cells[0]
    assert cell.returned == 6
    assert cell.title_matches == 6
    assert "ambigua" in _codes(report)
    suggestion = next(item.suggestion for item in report.warnings if item.code == "ambigua")
    assert "guardia" in suggestion
    assert "seguridad" in suggestion


def test_mostly_unmatched_titles_are_noise() -> None:
    titles = ["Analista de datos"] + [f"Guardia de turno {n}" for n in range(9)]
    report = measure_queries(
        _candidate(),
        ["Analista de datos"],
        ["demo"],
        lambda _source, _query: titles,
    )
    assert report.cells[0].returned == 10
    assert report.cells[0].title_matches == 1
    assert _codes(report) == {"ruido"}
    assert report.warnings[0].suggestion == NOISE_SUGGESTION


def test_empty_sources_warn_once() -> None:
    report = measure_queries(
        _candidate(),
        ["Analista de datos"],
        ["demo"],
        lambda _source, _query: [],
    )
    assert report.cells[0].returned == 0
    assert _codes(report) == {"vacía"}
    assert report.warnings[0].suggestion == EMPTY_SUGGESTION


def test_one_failing_source_does_not_fail_the_rest() -> None:
    def search(source: str, _query: str) -> list[str]:
        if source == "getonboard":
            raise RuntimeError("HTTP 400")
        return ["Analista de datos"]

    report = measure_queries(
        _candidate(),
        ["Analista de datos"],
        ["getonboard", "indeed"],
        search,
    )
    assert report.cells[0].error == "HTTP 400"
    assert report.cells[1].title_matches == 1
    assert report.cells[1].error is None


def test_measure_does_not_open_a_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    def _blocked(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("socket opened")

    monkeypatch.setattr(socket, "socket", _blocked)
    measure_queries(_candidate(), ["Analista"], ["demo"], lambda _s, _q: ["Analista"])


def _workspace(tmp_path: Path, project_root: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    data = tmp_path / "data"
    data.mkdir()
    (tmp_path / "output").mkdir()
    profile = data / "profile.yaml"
    example = project_root / "data" / "profile.example.yaml"
    raw = yaml.safe_load(example.read_text(encoding="utf-8"))
    raw["search_queries"] = ["Médico veterinario salud pública"]
    profile.write_text(yaml.safe_dump(raw, allow_unicode=True, sort_keys=False), encoding="utf-8")
    (tmp_path / ".jobbot.toml").write_text(
        f'[paths]\ntemplates = "{project_root / "templates"}"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    return profile


def test_cli_check_reports_split_and_leaves_profile_and_jobs(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    profile = _workspace(tmp_path, project_root, monkeypatch)
    before = profile.read_bytes()
    from jobbot.cli import run_cli
    from jobbot.config import load_config
    from jobbot.db.engine import make_engine, make_session_factory
    from jobbot.db.models import JobRow
    from jobbot.jobs.repository import JobRepository
    from jobbot.models.job import JobPosting

    config = load_config()
    session = make_session_factory(make_engine(config.database_path))()
    JobRepository(session).save(
        JobPosting(id="J0001", title="Analista", company="Acme", description="Informes")
    )
    session.commit()
    count = session.scalar(select(func.count()).select_from(JobRow))

    def search(source: str, _query: str, *, config: object) -> list[str]:
        del config
        if source == "getonboard":
            raise RuntimeError("HTTP 400")
        return ["Médico Veterinario Inspector", "Profesional Salud Pública"]

    monkeypatch.setattr("jobbot.profile.query_check.search_source_titles", search)
    code = run_cli(
        ["profile", "queries", "--check", "--source", "getonboard", "--source", "indeed"],
        standalone_mode=False,
    )
    out = capsys.readouterr().out

    assert code == SUCCESS
    assert "sin calce" in out
    assert "Dividir: probar" in out
    assert "error: HTTP 400" in out
    assert profile.read_bytes() == before
    again = make_session_factory(make_engine(config.database_path))()
    assert again.scalar(select(func.count()).select_from(JobRow)) == count


def test_cli_check_with_apply_exits_2_without_searching(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    called = False

    def search(*_args: object, **_kwargs: object) -> list[str]:
        nonlocal called
        called = True
        return []

    monkeypatch.setattr("jobbot.profile.query_check.search_source_titles", search)
    from jobbot.cli import run_cli

    code = run_cli(["profile", "queries", "--check", "--apply"], standalone_mode=False)
    assert code == VALIDATION_FAILURE
    assert called is False


def test_cli_unknown_source_exits_2(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    from jobbot.cli import run_cli

    code = run_cli(
        ["profile", "queries", "--check", "--source", "linkedin_post"],
        standalone_mode=False,
    )
    err = capsys.readouterr().err
    assert code == VALIDATION_FAILURE
    assert "getonboard" in err
