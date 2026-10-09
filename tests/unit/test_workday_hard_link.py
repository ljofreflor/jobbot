"""#215: `jobbot get` / `jobs add --url` read a Workday posting live through CXS."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from jobbot.exit_codes import SUCCESS, VALIDATION_FAILURE
from tests.conftest import plain_cli_text
from tests.fixtures.workday_http import (
    OPEN_PATH,
    SITE_URL,
    FakeWorkday,
    forbid_sockets,
    install,
    load_json,
)

POSTING_URL = (
    "https://paho.wd5.myworkdayjobs.com/en-US/pahocareers"
    "/job/Off-Site/National-PAHO-Consultant---Comunicaciones_Req-06070"
)
OPEN_DAY = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


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
    monkeypatch.setattr("jobbot.jobs.closing.utc_now", lambda: OPEN_DAY)
    forbid_sockets(monkeypatch)
    return tmp_path


def _serve(monkeypatch: pytest.MonkeyPatch, *, status: int = 200) -> FakeWorkday:
    fake = FakeWorkday()
    payload = load_json("error_403_s22.json") if status == 403 else load_json("detail_open.json")
    fake.detail(OPEN_PATH, payload, status=status)
    return install(monkeypatch, fake)


def _stored() -> list[object]:
    from jobbot.config import load_config
    from jobbot.db.engine import make_engine, make_session_factory
    from jobbot.jobs.repository import JobRepository

    session = make_session_factory(make_engine(load_config().database_path))()
    return list(JobRepository(session).list_all())


def _cli(*args: str) -> int:
    from jobbot.cli import run_cli

    return run_cli(list(args), standalone_mode=False)


def test_get_downloads_the_posting_through_cxs(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = _serve(monkeypatch)

    assert _cli("get", POSTING_URL) == SUCCESS

    out = plain_cli_text(capsys.readouterr().out)
    assert "Stored" in out
    assert [call.url for call in fake.cxs_calls] == [
        "https://paho.wd5.myworkdayjobs.com/wday/cxs/paho/pahocareers" + OPEN_PATH
    ]
    [job] = _stored()
    assert job.title == "National PAHO Consultant - Comunicaciones"  # type: ignore[attr-defined]
    assert job.source_job_id == "paho/pahocareers:Req-06070"  # type: ignore[attr-defined]
    assert job.closes_on.isoformat() == "2026-10-11"  # type: ignore[attr-defined]


def test_jobs_add_url_without_file_downloads_and_shows_the_closing(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _serve(monkeypatch)

    assert _cli("jobs", "add", "--url", POSTING_URL) == SUCCESS
    out = plain_cli_text(capsys.readouterr().out)
    assert "Added J0001" in out
    assert "Closes: 2026-10-11 23:59 (UTC-04:00)" in out

    assert _cli("jobs", "show", "J0001") == SUCCESS
    shown = plain_cli_text(capsys.readouterr().out)
    assert "Closes: 2026-10-11 23:59 (UTC-04:00)" in shown
    assert "Eastern Time" in shown
    assert "does not prefill the profile" in shown
    assert "questionnaire" in shown


def test_adding_the_same_url_twice_keeps_one_job(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _serve(monkeypatch)

    assert _cli("jobs", "add", "--url", POSTING_URL) == SUCCESS
    assert _cli("jobs", "add", "--url", SITE_URL + OPEN_PATH) == SUCCESS

    assert len(_stored()) == 1


def test_shortlist_flags_a_closing_within_three_days(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _serve(monkeypatch)
    assert _cli("jobs", "add", "--url", POSTING_URL) == SUCCESS
    monkeypatch.setattr(
        "jobbot.jobs.closing.utc_now", lambda: datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
    )
    capsys.readouterr()

    assert _cli("jobs", "shortlist") == SUCCESS

    out = plain_cli_text(capsys.readouterr().out)
    assert "J0001" in out
    assert "[cierra pronto: 2026-10-11 23:59" in out
    assert "UTC-04:00" in out


def test_closed_posting_is_not_stored(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _serve(monkeypatch, status=403)

    assert _cli("jobs", "add", "--url", POSTING_URL) == VALIDATION_FAILURE
    assert _cli("get", POSTING_URL) == VALIDATION_FAILURE

    captured = capsys.readouterr()
    assert "closed" in (captured.out + captured.err).casefold()
    assert "Recorded failure" not in captured.out + captured.err
    assert _stored() == []


def test_expired_closing_is_not_stored(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _serve(monkeypatch)
    monkeypatch.setattr(
        "jobbot.jobs.closing.utc_now", lambda: datetime(2026, 10, 13, 12, 0, tzinfo=UTC)
    )

    assert _cli("jobs", "add", "--url", POSTING_URL) == VALIDATION_FAILURE
    assert _stored() == []


def test_workday_url_without_a_posting_is_rejected_without_requests(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _serve(monkeypatch)

    assert _cli("jobs", "add", "--url", SITE_URL) == VALIDATION_FAILURE
    assert fake.cxs_calls == []


def test_closing_columns_are_added_to_an_existing_database(tmp_path: Path) -> None:
    from sqlalchemy import text

    from jobbot.db.engine import make_engine, make_session_factory
    from jobbot.jobs.repository import JobRepository
    from jobbot.models.job import JobPosting

    db_path = tmp_path / "legacy.sqlite"
    engine = make_engine(db_path)
    old = make_session_factory(engine)()
    JobRepository(old).add_from_text("Analyst\nAcme\nSQL and Excel.")
    old.close()
    with engine.begin() as conn:
        for column in ("closes_at", "closes_on", "closes_text", "ats_signals_json"):
            conn.execute(text(f"ALTER TABLE jobs DROP COLUMN {column}"))
    engine.dispose()

    repo = JobRepository(make_session_factory(make_engine(db_path))())
    loaded = repo.get("J0001")

    assert loaded is not None
    assert loaded.closes_on is None
    assert loaded.ats_signals == {}
    job = JobPosting(id="PENDING", title="Advisor", company="Acme", description="y")
    job.source_job_id = "acme:1"
    job.closes_text = "Closing Date: Oct 11"
    job.ats_signals = {"can_apply": True}
    stored = repo.get(repo.upsert_external(job).id)
    assert stored is not None
    assert stored.closes_text == "Closing Date: Oct 11"
    assert stored.ats_signals == {"can_apply": True}
