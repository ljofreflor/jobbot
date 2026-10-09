"""#207 / #205: `jobbot jobs check-open` persists the verdict; `shortlist` hides closed ones."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from jobbot.adapters.workday.cxs import HttpResponse
from jobbot.exit_codes import SUCCESS, VALIDATION_FAILURE
from jobbot.models.job import JobPosting
from tests.conftest import plain_cli_text
from tests.fixtures.check_open_http import (
    WORKDAY_API,
    WORKDAY_URL,
    FakeWeb,
    page,
    workday,
)
from tests.fixtures.workday_http import forbid_sockets

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)
GONE_URL = "https://careers.acme.test/jobs/77-coordinador"
QUIET_URL = "https://careers.acme.test/jobs/88-asistente"


@pytest.fixture
def workspace(tmp_path: Path, project_root: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    (tmp_path / "data").mkdir()
    (tmp_path / "output").mkdir()
    (tmp_path / "data" / "profile.yaml").write_text(
        (project_root / "data" / "profile.example.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (tmp_path / ".jobbot.toml").write_text(
        f'[paths]\ntemplates = "{project_root / "templates"}"\n', encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("JOBBOT_ROOT", raising=False)
    monkeypatch.setattr("jobbot.jobs.closing.utc_now", lambda: NOW)
    forbid_sockets(monkeypatch)
    return tmp_path


def _web(monkeypatch: pytest.MonkeyPatch) -> FakeWeb:
    import jobbot.adapters.workday.cxs as cxs

    web = (
        FakeWeb()
        .route(WORKDAY_API, 200, workday("detail_open.json"))
        .route(GONE_URL, 404, "")
        .route(QUIET_URL, 200, page("page_open.html"))
    )
    monkeypatch.setattr(cxs, "urllib_runner", web)
    monkeypatch.setattr(cxs, "pause", lambda _seconds: None)
    return web


def _repo():  # type: ignore[no-untyped-def]
    from jobbot.config import load_config
    from jobbot.db.engine import make_engine, make_session_factory
    from jobbot.jobs.repository import JobRepository

    return JobRepository(make_session_factory(make_engine(load_config().database_path))())


def _seed() -> None:
    repo = _repo()
    for job_id, title, url in (
        ("J0001", "Consultor Comunicaciones", WORKDAY_URL),
        ("J0002", "Coordinador de Proyectos", GONE_URL),
        ("J0003", "Asistente Administrativo", QUIET_URL),
    ):
        repo.save(
            JobPosting(
                id=job_id,
                source="manual",
                title=title,
                company="Acme",
                url=url,
                description=f"{title}. Reportes y coordinación.",
            )
        )


def _cli(*args: str) -> int:
    from jobbot.cli import run_cli

    return run_cli(list(args), standalone_mode=False)


def _db_hash(root: Path) -> str:
    return hashlib.sha256((root / "data" / "jobbot.sqlite").read_bytes()).hexdigest()


def test_without_ids_or_all_exits_2(workspace: Path) -> None:
    assert _cli("jobs", "check-open") == VALIDATION_FAILURE


def test_unknown_id_exits_2(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _web(monkeypatch)
    _seed()

    assert _cli("jobs", "check-open", "J0099") == VALIDATION_FAILURE


def test_all_persists_open_closed_unknown_with_evidence(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _web(monkeypatch)
    _seed()

    assert _cli("jobs", "check-open", "--all") == SUCCESS

    out = plain_cli_text(capsys.readouterr().out)
    assert "1 abierto, 1 cerrado, 1 desconocido" in out
    jobs = {job.id: job for job in _repo().list_all()}
    assert (jobs["J0001"].open_status, jobs["J0002"].open_status) == ("open", "closed")
    assert jobs["J0003"].open_status == "unknown"
    assert jobs["J0002"].open_evidence == "HTTP 404"
    assert jobs["J0002"].checked_at == NOW
    assert jobs["J0001"].closes_on == date(2026, 10, 11)


def test_dry_run_leaves_the_database_byte_for_byte(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _web(monkeypatch)
    _seed()
    before = _db_hash(workspace)

    assert _cli("jobs", "check-open", "--all", "--dry-run") == SUCCESS

    assert "Dry-run: nothing written" in plain_cli_text(capsys.readouterr().out)
    assert _db_hash(workspace) == before


def test_dry_run_without_a_database_creates_none(workspace: Path) -> None:
    assert _cli("jobs", "check-open", "--all", "--dry-run") == SUCCESS
    assert not (workspace / "data" / "jobbot.sqlite").exists()


def test_json_carries_the_full_url_status_and_checked_at(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _web(monkeypatch)
    _seed()
    capsys.readouterr()

    assert _cli("jobs", "check-open", "J0001", "J0002", "--json") == SUCCESS

    data = json.loads(capsys.readouterr().out)
    first = data["jobs"][0]
    assert first["url"] == WORKDAY_URL
    assert first["status"] == "open" and "canApply" in first["reason"]
    assert first["reason"] == first["evidence"]
    assert first["checked_at"].startswith("2026-10-05T12:00")
    assert data["jobs"][1]["status"] == "closed"


def test_all_keeps_going_when_one_posting_fails_and_encodes_accented_urls(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import jobbot.adapters.workday.cxs as cxs

    web = _web(monkeypatch)
    accented = "https://careers.acme.test/jobs/99-consultoría-actualización"
    web.route("https://careers.acme.test/jobs/99-consultor%C3%ADa-actualizaci%C3%B3n", 410)

    def wire(method: str, url: str, **kwargs: Any) -> HttpResponse:
        url.encode("ascii")
        if url == GONE_URL:
            raise RuntimeError("boom")
        return web(method, url, **kwargs)

    monkeypatch.setattr(cxs, "urllib_runner", wire)
    _seed()
    _repo().save(
        JobPosting(id="J0004", source="manual", title="Consultoría", company="Acme", url=accented)
    )

    assert _cli("jobs", "check-open", "--all") == SUCCESS

    jobs = {job.id: job for job in _repo().list_all()}
    assert jobs["J0002"].open_status == "unknown"
    assert jobs["J0002"].open_evidence == "error al verificar: RuntimeError: boom"
    assert (jobs["J0004"].open_status, jobs["J0004"].open_evidence) == ("closed", "HTTP 410")
    assert jobs["J0001"].open_status == "open"
    assert "1 abierto, 1 cerrado, 2 desconocido" in plain_cli_text(capsys.readouterr().out)


def test_network_failure_is_unknown_and_exit_0(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    web = _web(monkeypatch)
    web.routes[GONE_URL] = []
    web.route(GONE_URL, 0, "connection reset")
    _seed()

    assert _cli("jobs", "check-open", "J0002") == SUCCESS
    assert _repo().get("J0002").open_status == "unknown"  # type: ignore[union-attr]


def test_all_skips_closed_postings_checked_within_a_day(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    web = _web(monkeypatch)
    _seed()
    assert _cli("jobs", "check-open", "J0002") == SUCCESS
    web.calls.clear()
    monkeypatch.setattr("jobbot.jobs.closing.utc_now", lambda: NOW + timedelta(hours=3))

    assert _cli("jobs", "check-open", "--all") == SUCCESS

    assert GONE_URL not in web.urls()
    assert "1 omitidos" in plain_cli_text(capsys.readouterr().out)


def test_shortlist_hides_verified_closed_and_flags_closing_soon(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _web(monkeypatch)
    _seed()
    assert _cli("jobs", "check-open", "--all") == SUCCESS
    monkeypatch.setattr(
        "jobbot.jobs.closing.utc_now", lambda: datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
    )
    capsys.readouterr()

    assert _cli("jobs", "shortlist") == SUCCESS
    out = plain_cli_text(capsys.readouterr().out)
    assert "J0002" not in out
    assert "1 hidden: verified closed" in out
    assert "[cierra pronto: 2026-10-11 23:59" in out

    assert _cli("jobs", "shortlist", "--include-closed") == SUCCESS
    shown = plain_cli_text(capsys.readouterr().out)
    assert "J0002" in shown and "[cerrado, verificado 2026-10-05: HTTP 404]" in shown


def test_show_prints_the_last_online_check(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _web(monkeypatch)
    _seed()
    assert _cli("jobs", "check-open", "J0002") == SUCCESS
    capsys.readouterr()

    assert _cli("jobs", "show", "J0002") == SUCCESS

    assert "Online: cerrado, verificado 2026-10-05: HTTP 404" in plain_cli_text(
        capsys.readouterr().out
    )


def test_rediscovering_a_posting_keeps_its_online_check(workspace: Path) -> None:
    repo = _repo()
    repo.save(
        JobPosting(
            id="J0001", source="workday", source_job_id="t/s:Req-1", title="A", company="Acme"
        )
    )
    repo.record_open_check("J0001", status="closed", evidence="HTTP 404", checked_at=NOW)

    again = repo.upsert_external(
        JobPosting(
            id="PENDING", source="workday", source_job_id="t/s:Req-1", title="A", company="Acme"
        )
    )

    assert again.id == "J0001"
    assert again.open_status == "closed" and again.open_evidence == "HTTP 404"


def test_record_open_check_on_a_missing_job_raises(workspace: Path) -> None:
    with pytest.raises(KeyError):
        _repo().record_open_check("J0404", status="open", evidence="x", checked_at=NOW)
