"""An explicit --cdp host is the session that counts, including a foreign profile."""

from __future__ import annotations

import logging
from pathlib import Path
from urllib.error import URLError

import pytest

from jobbot.browser.sessions import (
    CdpSessionStatus,
    ChromeProcess,
    SessionStatus,
    inspect_sessions,
    probe_cdp_session,
    session_for,
)
from jobbot.exit_codes import SUCCESS

GREETING = "Hola, Caso Demo | Indeed"
INDEED = "https://cl.indeed.com/"


class RecordingFetch:
    def __init__(self, pages: list[dict[str, str]] | None = None, *, fail: bool = False) -> None:
        self.pages = pages or []
        self.fail = fail
        self.requested: list[str] = []

    def __call__(self, url: str) -> object:
        self.requested.append(url)
        if self.fail:
            raise URLError("connection refused")
        if url.endswith("/json/version"):
            return {"Browser": "Chrome/154.0"}
        return self.pages


def test_named_cdp_reads_a_foreign_profile_the_scan_does_not(tmp_path: Path) -> None:
    pages = [{"url": INDEED, "title": GREETING}]
    fetch = RecordingFetch(pages)
    report = probe_cdp_session("http://127.0.0.1:9222", "indeed", fetch=fetch)
    assert report.status is CdpSessionStatus.SIGNED_IN
    assert "Caso Demo" not in report.evidence

    scan = RecordingFetch(pages)
    foreign = ChromeProcess(pid=4242, profile_dir=Path("/elsewhere/other-profile"), cdp_port=9222)
    states = inspect_sessions(
        tmp_path,
        sites=["indeed"],
        ports=(9222,),
        fetch=scan,
        processes=[foreign],
    )
    state = session_for(states, "indeed")
    assert state is not None
    assert state.status is not SessionStatus.READY
    assert state.cdp_url is None
    assert "not read" in state.evidence
    assert scan.requested == []


def test_ipv6_endpoint_is_the_one_queried() -> None:
    fetch = RecordingFetch([{"url": INDEED, "title": GREETING}])
    report = probe_cdp_session("http://[::1]:9222", "indeed", fetch=fetch)
    assert report.status is CdpSessionStatus.SIGNED_IN
    assert report.url == "http://[::1]:9222"
    assert fetch.requested
    assert all(url.startswith("http://[::1]:9222/") for url in fetch.requested)
    assert not any("127.0.0.1" in url for url in fetch.requested)


def test_a_plain_page_is_not_signed_in_and_silence_is_unreachable() -> None:
    plain = probe_cdp_session(
        "http://127.0.0.1:9222",
        "indeed",
        fetch=RecordingFetch([{"url": INDEED, "title": "Empleos"}]),
    )
    assert plain.status is CdpSessionStatus.NOT_SIGNED_IN
    silent = probe_cdp_session(
        "http://127.0.0.1:9222",
        "indeed",
        fetch=RecordingFetch(fail=True),
    )
    assert silent.status is CdpSessionStatus.UNREACHABLE
    assert silent.evidence == "endpoint did not answer"
    assert "not signed in" not in silent.evidence
    assert "sin sesión" not in silent.evidence


def test_cookie_presence_signs_in_without_keeping_the_value() -> None:
    report = probe_cdp_session(
        "http://127.0.0.1:9222",
        "indeed",
        fetch=RecordingFetch([{"url": INDEED, "title": "Empleos"}]),
        cookie_names=lambda _url: ["SHOE"],
    )
    assert report.status is CdpSessionStatus.SIGNED_IN
    assert "SHOE" not in report.evidence


def test_a_greeting_in_the_markup_is_not_a_session() -> None:
    from jobbot.adapters.indeed.client import indeed_session_authenticated

    assert (
        indeed_session_authenticated(
            url=INDEED,
            html="<p>Hola, nos alegra verte de vuelta</p>",
            cookie_names=["CTK"],
        )
        is False
    )


def test_a_job_tab_that_greets_in_its_title_is_not_a_session() -> None:
    report = probe_cdp_session(
        "http://127.0.0.1:9222",
        "indeed",
        fetch=RecordingFetch(
            [
                {
                    "url": f"{INDEED}viewjob?jk=abc123def456",
                    "title": "Hola, buscamos analista - Estudio Neutro - Empleo | Indeed.com",
                }
            ]
        ),
    )
    assert report.status is CdpSessionStatus.NOT_SIGNED_IN


def _stored_indeed_job(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> str:
    (tmp_path / "data").mkdir()
    (tmp_path / "output").mkdir()
    (tmp_path / "data" / "profile.yaml").write_text(
        (project_root / "data" / "profile.example.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    (tmp_path / ".jobbot.toml").write_text(
        f'[paths]\ntemplates = "{project_root / "templates"}"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    import jobbot.cli as cli
    from jobbot.db.engine import make_engine, make_session_factory
    from jobbot.jobs.repository import JobRepository
    from jobbot.models.job import JobPosting

    monkeypatch.setattr(
        "jobbot.jobs.closure.fetch_posting_text",
        lambda _url, **_k: "<html>still open</html>",
    )
    config = cli.load_config()
    session = make_session_factory(make_engine(config.database_path))()
    url = "https://cl.indeed.com/viewjob?jk=abc123def456"
    stored = JobRepository(session).upsert_external(
        JobPosting.model_validate(
            {
                "id": "PENDING",
                "source": "indeed",
                "title": "Analyst",
                "company": "Estudio Neutro",
                "url": url,
                "ats_url": url,
                "ats_kind": "indeed",
                "description": "Una descripción.",
            }
        )
    )
    return stored.id


def test_greeting_name_stays_out_of_apply_output(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    import jobbot.browser.sessions as sessions
    from jobbot.cli import run_cli

    job_id = _stored_indeed_job(tmp_path, project_root, monkeypatch)
    fetch = RecordingFetch([{"url": INDEED, "title": GREETING}])
    monkeypatch.setattr(sessions, "fetch_local_json", fetch)

    with caplog.at_level(logging.DEBUG):
        code = run_cli(
            ["application", "apply", job_id, "--cdp", "http://[::1]:9222"],
            standalone_mode=False,
        )

    captured = capsys.readouterr()
    text = captured.out + captured.err + caplog.text
    assert code == SUCCESS
    assert "signed in" in captured.out
    assert "[::1]" in captured.out
    assert "127.0.0.1" not in captured.out
    assert "Caso Demo" not in text
    assert all(item.startswith("http://[::1]:9222/") for item in fetch.requested)


def test_a_non_local_cdp_host_does_not_abort_apply(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from jobbot.cli import run_cli

    report = probe_cdp_session("http://host.docker.internal:9222", "indeed")
    assert report.status is CdpSessionStatus.UNREACHABLE
    assert report.evidence == "endpoint is not a local host"

    job_id = _stored_indeed_job(tmp_path, project_root, monkeypatch)
    code = run_cli(
        ["application", "apply", job_id, "--cdp", "http://host.docker.internal:9222"],
        standalone_mode=False,
    )

    captured = capsys.readouterr()
    assert code == SUCCESS
    assert "unreachable" in captured.out
