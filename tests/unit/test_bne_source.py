"""Bolsa Nacional de Empleo: public JSON, no empty retry. No network."""

from __future__ import annotations

import json
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml

from jobbot.adapters.bne.parse import job_from_row
from jobbot.cli import run_cli
from jobbot.portals.detect import JOB_BOARD_KINDS, AtsKind, detect_ats

FIXTURES = Path("tests/fixtures/bne")
POSTED = datetime(2026, 10, 6, tzinfo=ZoneInfo("America/Santiago"))
OFFER = "https://www.bne.cl/oferta/2026-000001"


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
    monkeypatch.setattr("jobbot.adapters.bne.discover.fetch_public", fetch)
    monkeypatch.setattr("jobbot.adapters.bne.discover.pause", lambda: None)


def _body(project_root: Path, name: str) -> str:
    return (project_root / FIXTURES / name).read_text(encoding="utf-8")


def test_dry_run_lists_forty_and_writes_nothing(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    page = _body(project_root, "buscar_abogado.json")

    def fetch(url: str) -> tuple[int, str, str]:
        return 200, page, url

    _install(monkeypatch, fetch)
    code = run_cli(
        ["jobs", "discover", "--source", "bne", "--query", "abogado", "--dry-run"],
        standalone_mode=False,
    )
    captured = capsys.readouterr()
    assert code == 0
    assert "bne: 40 avisos" in captured.out
    assert "Health advisor" in captured.out
    assert "Acme" in captured.out
    assert "Santiago" in captured.out
    assert "Nothing written." in captured.out
    row = json.loads(page)["paginaOfertas"]["resultados"][0]
    job = job_from_row(row)
    assert job is not None
    assert job.url == "https://www.bne.cl/oferta/2026-000001"
    assert job.posted_at == POSTED
    assert job.note == "API/Externo"
    assert list((tmp_path / "output" / "jobs").glob("*/job.json")) == []


def test_zero_results_do_not_retry(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    page = _body(project_root, "buscar_jefe_juridico_cero.json")
    calls: list[str] = []

    def fetch(url: str) -> tuple[int, str, str]:
        calls.append(url)
        return 200, page, url

    _install(monkeypatch, fetch)
    code = run_cli(
        ["jobs", "discover", "--source", "bne", "--query", "jefe juridico", "--dry-run"],
        standalone_mode=False,
    )
    captured = capsys.readouterr()
    assert code == 0
    assert len(calls) == 1
    assert "textoLibre=jefe%20juridico" in calls[0]
    assert "textoLibre=&" not in calls[0]
    assert '0 resultados para "jefe juridico"' in captured.out
    assert list((tmp_path / "output" / "jobs").glob("*/job.json")) == []


def test_an_ignored_filter_stores_nothing(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    page = _body(project_root, "buscar_filtro_ignorado.json")

    def fetch(url: str) -> tuple[int, str, str]:
        return 200, page, url

    _install(monkeypatch, fetch)
    code = run_cli(
        ["jobs", "discover", "--source", "bne", "--query", "abogado"],
        standalone_mode=False,
    )
    captured = capsys.readouterr()
    assert code == 0
    assert "filtro ignorado" in captured.out
    assert list((tmp_path / "output" / "jobs").glob("*/job.json")) == []


def test_a_hidden_employer_is_confidential() -> None:
    job = job_from_row(
        {
            "codigo": "2026-000002",
            "titulo": "Office analyst",
            "empresa": "Hidden",
            "mostrarEmpresa": False,
            "fecha": "06/10/26",
            "comuna": "Santiago",
            "region": "Metropolitana",
        }
    )
    assert job is not None
    assert job.company == "Confidencial"


def test_three_pages_stop_at_the_third(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    pages = {str(n): _body(project_root, f"buscar_page{n}.json") for n in (1, 2, 3)}
    calls: list[str] = []

    def fetch(url: str) -> tuple[int, str, str]:
        calls.append(url)
        for number, body in pages.items():
            if f"numPaginaRecuperar={number}&" in url:
                return 200, body, url
        raise AssertionError(url)

    _install(monkeypatch, fetch)
    code = run_cli(
        [
            "jobs",
            "discover",
            "--source",
            "bne",
            "--query",
            "abogado",
            "--limit",
            "120",
            "--dry-run",
        ],
        standalone_mode=False,
    )
    assert code == 0
    assert any("numPaginaRecuperar=1&" in url for url in calls)
    assert any("numPaginaRecuperar=2&" in url for url in calls)
    assert any("numPaginaRecuperar=3&" in url for url in calls)
    assert not any("numPaginaRecuperar=4" in url for url in calls)


def test_learning_an_offer_stays_a_board(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert detect_ats(OFFER) is AtsKind.BNE
    assert AtsKind.BNE in JOB_BOARD_KINDS
    _workspace(tmp_path, project_root, monkeypatch)

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("socket")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    code = run_cli(["companies", "learn", OFFER, "--company", "Acme"], standalone_mode=False)
    captured = capsys.readouterr()
    assert code == 0
    assert "Not company-specific" in captured.out
    assert not (tmp_path / "data" / "companies.yaml").exists()


def test_a_changed_shape_exits_5(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    page = _body(project_root, "buscar_forma_cambiada.json")

    def fetch(url: str) -> tuple[int, str, str]:
        return 200, page, url

    _install(monkeypatch, fetch)
    code = run_cli(
        ["jobs", "discover", "--source", "bne", "--query", "abogado", "--dry-run"],
        standalone_mode=False,
    )
    assert code == 5
