"""`jobbot jobs discover --source workday`: preview, store, dedupe, partial failures (#225)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml

from jobbot.exit_codes import GENERIC_FAILURE, SUCCESS, UI_CHANGED, VALIDATION_FAILURE
from tests.conftest import plain_cli_text
from tests.fixtures.workday_http import (
    OPEN_PATH,
    SITE_URL,
    FakeWorkday,
    fixture_text,
    forbid_sockets,
    install,
    load_json,
    paged_search,
    serve_every_detail,
)

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=UTC)


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("JOBBOT_ROOT", raising=False)
    monkeypatch.setattr("jobbot.jobs.closing.utc_now", lambda: NOW)
    forbid_sockets(monkeypatch)
    return tmp_path


def _open_site(monkeypatch: pytest.MonkeyPatch) -> FakeWorkday:
    page = load_json("search_page1.json")
    fake = FakeWorkday(pages=[page])
    serve_every_detail(fake, page)
    return install(monkeypatch, fake)


def _run(*args: str) -> int:
    from jobbot.cli import run_cli

    return run_cli(["jobs", "discover", "--source", "workday", *args], standalone_mode=False)


def _stored(root: Path) -> list[str]:
    from jobbot.config import load_config
    from jobbot.db.engine import make_engine, make_session_factory
    from jobbot.jobs.repository import JobRepository

    session = make_session_factory(make_engine(load_config(root).database_path))()
    return [job.source_job_id or "" for job in JobRepository(session).list_all()]


def test_dry_run_shows_the_table_and_writes_nothing(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = _open_site(monkeypatch)

    code = _run("--site", SITE_URL, "--query", "epidemiology", "--dry-run")

    out = plain_cli_text(capsys.readouterr().out)
    assert code == SUCCESS
    assert "(dry-run)" in out and "Nothing written" in out
    assert "National PAHO Consultant" in out and "Off Site" in out
    assert "2026-10-11 23:59" in out
    assert fake.cxs_calls[0].body is not None
    assert fake.cxs_calls[0].body["searchText"] == "epidemiology"
    assert not (workspace / "data" / "jobbot.sqlite").exists()
    assert not (workspace / "data" / "companies.yaml").exists()
    assert not (workspace / "output" / "jobs").exists()


def test_store_then_rediscover_updates_without_duplicating(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _open_site(monkeypatch)

    assert _run("--site", SITE_URL, "--query", "health") == SUCCESS
    first = _stored(workspace)
    assert _run("--site", SITE_URL, "--query", "health", "--dry-run") == SUCCESS
    preview = plain_cli_text(capsys.readouterr().out)
    assert _run("--site", SITE_URL, "--query", "health") == SUCCESS

    assert sorted(first) == sorted(_stored(workspace))
    assert "paho/pahocareers:Req-06070" in first
    assert "actualizar J0002" in preview
    job_json = json.loads(
        (workspace / "output" / "jobs" / "J0002" / "job.json").read_text(encoding="utf-8")
    )
    assert job_json["closes_on"] == "2026-10-11"
    assert job_json["ats_signals"]["resume_parsing"] is False
    companies = yaml.safe_load((workspace / "data" / "companies.yaml").read_text("utf-8"))
    assert "myworkdayjobs.com" in json.dumps(companies)


def test_closing_within_three_days_is_flagged(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        "jobbot.jobs.closing.utc_now", lambda: datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
    )
    _open_site(monkeypatch)

    assert _run("--site", SITE_URL, "--query", "x", "--dry-run") == SUCCESS

    assert "guardar · cierra pronto" in plain_cli_text(capsys.readouterr().out)


def test_pages_until_total_and_stores_every_posting(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = install(monkeypatch, FakeWorkday(pages=paged_search(45)))

    code = _run("--site", SITE_URL, "--query", "x", "--limit", "50", "--no-details")

    assert code == SUCCESS
    assert [c.body["offset"] for c in fake.cxs_calls if c.body] == [0, 20, 40]
    assert len(_stored(workspace)) == 45


def test_expired_and_closed_postings_are_not_stored_as_open(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    expired = load_json("detail_open.json")
    expired["jobPostingInfo"]["jobDescription"] = "<p>Closing Date:</p>January 2, 2020, 5:00 PM UTC"
    fake = FakeWorkday(pages=[load_json("search_page1.json")])
    fake.detail(OPEN_PATH, expired)
    fake.details["/job/Washington-DC/PAHO-Internships_Req-05839"] = (
        403,
        fixture_text("error_403_s22.json"),
    )
    install(monkeypatch, fake)

    assert _run("--site", SITE_URL, "--query", "x") == SUCCESS

    out = plain_cli_text(capsys.readouterr().out)
    assert "cierre vencido" in out
    assert "no admite postulación" in out
    stored = _stored(workspace)
    assert "paho/pahocareers:Req-06070" not in stored
    assert "paho/pahocareers:Req-05839" not in stored


def test_one_site_failing_does_not_cancel_the_others(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    import jobbot.adapters.workday.cxs as cxs

    good = FakeWorkday(pages=paged_search(2))
    bad = FakeWorkday(search_status=403)

    def route(method: str, url: str, **kwargs: object) -> cxs.HttpResponse:
        target = bad if "broken.wd1" in url else good
        return target(method, url, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(cxs, "urllib_runner", route)
    monkeypatch.setattr(cxs, "pause", lambda _s: None)

    code = _run(
        "--site",
        "https://broken.wd1.myworkdayjobs.com/External",
        "--site",
        SITE_URL,
        "--query",
        "x",
        "--no-details",
    )

    out = plain_cli_text(capsys.readouterr().out)
    assert code == SUCCESS
    assert "broken/External «x»: falló (broken/External: HTTP 403 errorCode S22)" in out
    assert len(_stored(workspace)) == 2


def test_every_site_failing_is_a_failure(workspace: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    install(monkeypatch, FakeWorkday(search_status=500))

    assert _run("--site", SITE_URL, "--query", "x", "--dry-run") == GENERIC_FAILURE


def test_robots_disallow_reports_the_omission_and_makes_no_cxs_request(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fake = install(monkeypatch, FakeWorkday(robots=fixture_text("robots_disallow.txt")))

    code = _run("--site", SITE_URL, "--query", "x", "--dry-run")

    assert code == GENERIC_FAILURE
    assert fake.cxs_calls == []
    assert "bloqueado: robots" in plain_cli_text(capsys.readouterr().out)


def test_changed_json_on_the_only_site_is_ui_changed(
    workspace: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install(monkeypatch, FakeWorkday(pages=[{"surprise": []}]))

    assert _run("--site", SITE_URL, "--query", "x", "--no-details") == UI_CHANGED


@pytest.mark.parametrize(
    "args",
    [
        ("--site", "https://example.org/careers", "--query", "x"),
        ("--site", SITE_URL, "--query", "x", "--limit", "0"),
        ("--site", SITE_URL, "--query", "x", "--limit", "201"),
    ],
)
def test_invalid_flags_are_validation_failures_without_requests(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, args: tuple[str, ...]
) -> None:
    fake = install(monkeypatch, FakeWorkday())

    assert _run(*args) == VALIDATION_FAILURE
    assert fake.calls == []


def test_unknown_source_is_a_validation_failure(workspace: Path) -> None:
    from jobbot.cli import run_cli

    args = ["jobs", "discover", "--source", "nope", "--query", "x"]
    assert run_cli(args, standalone_mode=False) == VALIDATION_FAILURE


def test_without_site_reads_registered_workday_sites(
    workspace: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from jobbot.cli import run_cli

    learn = ["companies", "learn", SITE_URL, "--company", "Acme Health"]
    assert run_cli(learn, standalone_mode=False) == SUCCESS
    fake = install(monkeypatch, FakeWorkday(pages=paged_search(1)))

    assert _run("--query", "x", "--dry-run", "--no-details") == SUCCESS

    assert fake.cxs_calls[0].url.endswith("/wday/cxs/paho/pahocareers/jobs")
    assert "Consultant 000" in plain_cli_text(capsys.readouterr().out)


def test_without_any_site_says_how_to_register_one(workspace: Path) -> None:
    assert _run("--query", "x", "--dry-run") == VALIDATION_FAILURE


def test_get_job_source_knows_workday() -> None:
    from jobbot.adapters.workday.jobs import WorkdayJobSource
    from jobbot.config import JobbotConfig
    from jobbot.jobs.discover import source_names
    from jobbot.jobs.sources import get_job_source

    assert isinstance(get_job_source("workday", JobbotConfig()), WorkdayJobSource)
    assert "workday" in source_names()


def test_job_source_search_and_get_by_url(monkeypatch: pytest.MonkeyPatch) -> None:
    from jobbot.adapters.workday.jobs import WorkdayJobSource
    from jobbot.jobs.sources import JobSearchQuery

    forbid_sockets(monkeypatch)
    fake = install(monkeypatch, FakeWorkday(pages=[load_json("search_page1.json")]))
    fake.detail(OPEN_PATH, load_json("detail_open.json"))
    source = WorkdayJobSource([SITE_URL])

    found = source.search_jobs(JobSearchQuery(query="health", limit=4))
    one = source.get_job(SITE_URL + OPEN_PATH)

    assert len(found) == 4
    assert one.closes_text is not None
    with pytest.raises(ValueError):
        source.get_job("J0001")
