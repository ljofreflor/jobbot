"""A public bases PDF becomes one posting; an index only lists matching links."""

from __future__ import annotations

import json
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml

from jobbot.cli import run_cli
from jobbot.jobs.pdf_posting import PublicBody, posting_identity
from tests.fixtures.cv_pdf import build_pdf, content_stream, write_scanned_cv

PAGE = "https://municipio-ejemplo.cl/transparencia"
PDF_URL = "https://municipio-ejemplo.cl/docs/bases_concurso_apoyo.pdf"
_PAD = (
    "El presente documento describe las bases del llamado. "
    "Los antecedentes se reciben en la oficina de partes. "
    "Se requiere formacion acorde al cargo y experiencia en atencion de publico. "
    "El proceso es publico y las bases completas estan en este archivo. "
    "Quien postula declara conocer el plazo y las condiciones generales."
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


def _pdf(path: Path, *lines: str) -> bytes:
    text = "\n".join((*lines, _PAD))
    build_pdf([content_stream(text)], path)
    return path.read_bytes()


def _body(data: bytes, *, content_type: str, url: str = PDF_URL) -> PublicBody:
    return PublicBody(status=200, body=data, content_type=content_type, final_url=url)


def _install(
    monkeypatch: pytest.MonkeyPatch,
    fetched: PublicBody,
) -> None:
    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("socket")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    monkeypatch.setattr("jobbot.jobs.pdf_posting.fetch_public", lambda _url: fetched)


def _stored(tmp_path: Path) -> list[dict[str, object]]:
    paths = sorted((tmp_path / "output" / "jobs").glob("*/job.json"))
    return [json.loads(path.read_text(encoding="utf-8")) for path in paths]


def test_a_text_pdf_stores_the_santiago_closing(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    data = _pdf(
        tmp_path / "bases.pdf",
        "Municipalidad de Ejemplo",
        "Concurso para un cargo de apoyo administrativo",
        "Plazo de postulación hasta el 30 de octubre de 2026",
    )
    _install(monkeypatch, _body(data, content_type="application/pdf"))
    code = run_cli(["jobs", "add", "--url", PDF_URL], standalone_mode=False)
    assert code == 0
    stored = _stored(tmp_path)
    assert len(stored) == 1
    job = stored[0]
    assert job["source"] == "pdf"
    assert job["source_job_id"] == posting_identity(PDF_URL)
    assert job["url"] == PDF_URL
    assert job["company"] == "Municipalidad de Ejemplo"
    assert "Concurso para un cargo" in str(job["title"])
    got = datetime.fromisoformat(str(job["closes_at"]))
    want = datetime(2026, 10, 30, 23, 59, 59, tzinfo=ZoneInfo("America/Santiago"))
    assert got == want
    assert "Added" in capsys.readouterr().out


def test_a_scanned_pdf_is_refused(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    scanned = tmp_path / "scan.pdf"
    write_scanned_cv(scanned)
    _install(monkeypatch, _body(scanned.read_bytes(), content_type="application/pdf"))
    code = run_cli(["jobs", "add", "--url", PDF_URL], standalone_mode=False)
    captured = capsys.readouterr()
    assert code == 2
    assert "capa de texto" in captured.err
    assert "jobs add --file" in captured.err
    assert _stored(tmp_path) == []


def test_octet_stream_with_pdf_magic_is_a_pdf(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    data = _pdf(
        tmp_path / "bases.pdf",
        "Municipalidad de Ejemplo",
        "Concurso publico",
        "Plazo de postulacion hasta el 30 de octubre de 2026",
    )
    _install(monkeypatch, _body(data, content_type="application/octet-stream"))
    code = run_cli(["jobs", "add", "--url", PDF_URL], standalone_mode=False)
    assert code == 0
    assert _stored(tmp_path)[0]["source"] == "pdf"


def test_a_pdf_without_a_closing_date_says_it_cannot_be_checked(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    data = _pdf(tmp_path / "bases.pdf", "Municipalidad de Ejemplo", "Concurso publico")
    _install(monkeypatch, _body(data, content_type="application/pdf"))
    code = run_cli(["jobs", "add", "--url", PDF_URL], standalone_mode=False)
    captured = capsys.readouterr()
    assert code == 0
    job = _stored(tmp_path)[0]
    assert job["closes_at"] is None
    assert "vigencia no verificable (#207)" in captured.out


def test_a_deserted_contest_is_not_stored(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    data = _pdf(
        tmp_path / "bases.pdf",
        "Municipalidad de Ejemplo",
        "Este concurso declarado desierto.",
    )
    _install(monkeypatch, _body(data, content_type="application/pdf"))
    code = run_cli(["jobs", "add", "--url", PDF_URL], standalone_mode=False)
    assert code == 2
    assert _stored(tmp_path) == []


def test_the_same_pdf_twice_does_not_duplicate(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    data = _pdf(
        tmp_path / "bases.pdf",
        "Municipalidad de Ejemplo",
        "Concurso publico",
        "Plazo de postulacion hasta el 30 de octubre de 2026",
    )
    _install(monkeypatch, _body(data, content_type="application/pdf"))
    assert run_cli(["jobs", "add", "--url", PDF_URL], standalone_mode=False) == 0
    assert run_cli(["jobs", "add", "--url", PDF_URL], standalone_mode=False) == 0
    stored = _stored(tmp_path)
    assert len(stored) == 1
    assert stored[0]["source_job_id"] == posting_identity(PDF_URL)


def test_pdf_index_dry_run_lists_the_two_matching_links(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    html = (project_root / "tests/fixtures/pdf_concursos/transparencia_index.html").read_text(
        encoding="utf-8"
    )

    def refuse(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("socket")

    monkeypatch.setattr(urllib.request, "urlopen", refuse)
    monkeypatch.setattr("jobbot.jobs.pdf_index.fetch_page", lambda _url: html)
    code = run_cli(
        ["jobs", "discover", "--source", "pdf-index", "--url", PAGE, "--dry-run"],
        standalone_mode=False,
    )
    captured = capsys.readouterr()
    assert code == 0
    assert captured.out.count(".pdf") == 2
    assert "bases_concurso_apoyo.pdf" in captured.out
    assert "concurso_turno.pdf" in captured.out
    assert "aviso.pdf" not in captured.out
    assert "Nothing written." in captured.out
    assert list((tmp_path / "output" / "jobs").glob("*/job.json")) == []
    assert list((tmp_path / "data").glob("*.sqlite*")) == []
