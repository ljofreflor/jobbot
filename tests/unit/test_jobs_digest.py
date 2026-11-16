"""jobs digest: a shareable summary that stores nothing and sends nothing (issue #282)."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml

from jobbot.exit_codes import SUCCESS, VALIDATION_FAILURE
from jobbot.jobs.digest import (
    WHATSAPP_LIMIT,
    DigestEntry,
    load_last_digest,
    render_whatsapp,
    resolve_timezone,
    select_entries,
)
from jobbot.models.job import JobPosting

NY = ZoneInfo("America/New_York")
SANTIAGO = ZoneInfo("America/Santiago")
NOW = datetime(2026, 10, 18, 15, 0, tzinfo=UTC)


def _job(
    job_id: str,
    *,
    discovered: datetime,
    closes: datetime | None = None,
    status: str | None = None,
    note: str | None = None,
    url: str = "https://jobs.example.org/aviso",
    title: str = "Analista",
    description: str = "",
) -> JobPosting:
    return JobPosting(
        id=job_id,
        title=title,
        company="Instituto Ejemplo",
        url=url,
        description=description,
        discovered_at=discovered,
        closes_at=closes,
        open_status=status,
        note=note,
    )


def test_only_new_open_postings_sorted_by_closing() -> None:
    since = datetime(2026, 10, 17, tzinfo=SANTIAGO)
    fresh = datetime(2026, 10, 18, 12, tzinfo=UTC)
    early = datetime(2026, 10, 20, 18, tzinfo=UTC)
    later = datetime(2026, 10, 28, 18, tzinfo=UTC)
    jobs = [
        _job("J1", discovered=fresh, closes=later, title="Tarde"),
        _job("J2", discovered=fresh, closes=early, title="Pronto"),
        _job("J3", discovered=fresh, status="closed", title="Cerrado"),
        _job("J4", discovered=fresh, title="No admisible"),
        _job("J5", discovered=datetime(2026, 10, 1, tzinfo=UTC), title="Antiguo"),
    ]
    entries = select_entries(
        jobs,
        since=since,
        zone=SANTIAGO,
        eligibility={"J4": "no_admisible"},
        reasons={},
        include_doubtful=False,
        limit=10,
    )
    assert [entry.title for entry in entries] == ["Pronto", "Tarde"]


def test_new_york_close_is_shown_in_chile() -> None:
    closes = datetime(2026, 10, 15, 23, 59, tzinfo=NY)
    job = _job("J1", discovered=datetime(2026, 10, 18, tzinfo=UTC), closes=closes)
    entry = select_entries(
        [job],
        since=datetime(2026, 10, 1, tzinfo=UTC),
        zone=SANTIAGO,
        eligibility={},
        reasons={},
        include_doubtful=False,
        limit=10,
    )[0]
    assert "16-10 00:59 (Chile)" in entry.closing
    assert "America/New_York" in entry.closing


def test_missing_salary_is_named() -> None:
    job = _job("J1", discovered=datetime(2026, 10, 18, tzinfo=UTC))
    entry = select_entries(
        [job],
        since=datetime(2026, 10, 1, tzinfo=UTC),
        zone=SANTIAGO,
        eligibility={},
        reasons={},
        include_doubtful=False,
        limit=10,
    )[0]
    assert entry.salary == "renta no publicada"


def test_internal_note_is_not_in_the_message() -> None:
    job = _job(
        "J1",
        discovered=datetime(2026, 10, 18, tzinfo=UTC),
        note="escribir a persona@example.org",
        url="https://jobs.example.org/aviso?utm_source=mail",
    )
    entry = select_entries(
        [job],
        since=datetime(2026, 10, 1, tzinfo=UTC),
        zone=SANTIAGO,
        eligibility={},
        reasons={},
        include_doubtful=False,
        limit=10,
    )[0]
    text = "\n".join(render_whatsapp([entry], since=NOW))
    assert "example.org" not in text.split("jobs.example.org")[-1] or "persona@" not in text
    assert "persona@" not in text
    assert "utm_source" not in text
    assert entry.url == "https://jobs.example.org/aviso"


def test_whatsapp_messages_stay_within_the_limit() -> None:
    entries = [
        DigestEntry(
            job_id=f"J{index}",
            title="Cargo " + ("largo " * 40),
            company="Instituto Ejemplo",
            salary="renta no publicada",
            closing="cierre no informado",
            url=f"https://jobs.example.org/{index}",
        )
        for index in range(30)
    ]
    messages = render_whatsapp(entries, since=NOW)
    assert len(messages) > 1
    assert all(len(message) <= WHATSAPP_LIMIT for message in messages)
    assert messages[0].startswith("(1/")
    assert messages[-1].startswith(f"({len(messages)}/{len(messages)})")


def test_second_digest_keeps_only_later_postings(tmp_path: Path) -> None:
    from jobbot.jobs.digest import save_last_digest

    state = tmp_path / "digest_state.json"
    first = datetime(2026, 10, 18, 12, tzinfo=UTC)
    save_last_digest(state, first)
    old = _job("J1", discovered=datetime(2026, 10, 18, 11, tzinfo=UTC), title="Ya visto")
    new = _job("J2", discovered=datetime(2026, 10, 18, 13, tzinfo=UTC), title="Posterior")
    entries = select_entries(
        [old, new],
        since=load_last_digest(state) or first,
        zone=SANTIAGO,
        eligibility={},
        reasons={},
        include_doubtful=False,
        limit=10,
    )
    assert [entry.title for entry in entries] == ["Posterior"]


def test_unknown_timezone_is_rejected(tmp_path: Path) -> None:
    from jobbot.config import JobbotConfig

    config = JobbotConfig(root=tmp_path)
    with pytest.raises(Exception, match="zona horaria"):
        resolve_timezone(config, country="AR")


def _workspace(tmp_path: Path, project_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data = tmp_path / "data"
    data.mkdir()
    (tmp_path / "output").mkdir()
    raw = yaml.safe_load(
        (project_root / "data" / "profile.example.yaml").read_text(encoding="utf-8")
    )
    (data / "profile.yaml").write_text(
        yaml.safe_dump(raw, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    (data / "eligibility.yaml").write_text("J4: no_admisible\n", encoding="utf-8")
    (tmp_path / ".jobbot.toml").write_text(
        f'[paths]\ntemplates = "{project_root / "templates"}"\n',
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)


def test_cli_digest_lists_only_the_two_open_postings(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    from jobbot.cli import run_cli
    from jobbot.config import load_config
    from jobbot.db.engine import make_engine, make_session_factory
    from jobbot.jobs.repository import JobRepository

    config = load_config()
    session = make_session_factory(make_engine(config.database_path))()
    fresh = datetime(2026, 10, 18, 12, tzinfo=UTC)
    jobs = [
        _job("J1", discovered=fresh, closes=datetime(2026, 10, 28, 18, tzinfo=UTC), title="Tarde"),
        _job("J2", discovered=fresh, closes=datetime(2026, 10, 20, 18, tzinfo=UTC), title="Pronto"),
        _job("J3", discovered=fresh, status="closed", title="Cerrado"),
        _job(
            "J4",
            discovered=fresh,
            title="No admisible",
            note="escribir a persona@example.org",
        ),
        _job("J5", discovered=datetime(2026, 10, 1, tzinfo=UTC), title="Antiguo"),
    ]
    repo = JobRepository(session)
    for job in jobs:
        repo.save(job)
    session.commit()

    code = run_cli(
        ["jobs", "digest", "--since", "2026-10-17", "--format", "whatsapp"],
        standalone_mode=False,
    )
    out = capsys.readouterr().out
    assert code == SUCCESS
    assert out.index("Pronto") < out.index("Tarde")
    assert "Cerrado" not in out
    assert "No admisible" not in out
    assert "Antiguo" not in out
    assert "persona@" not in out

    again = run_cli(["jobs", "digest", "--format", "whatsapp"], standalone_mode=False)
    second = capsys.readouterr().out
    assert again == SUCCESS
    assert "sin oportunidades nuevas desde" in second
    assert "Pronto" not in second


def test_cli_rejects_an_output_outside_output(
    tmp_path: Path,
    project_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _workspace(tmp_path, project_root, monkeypatch)
    from jobbot.cli import run_cli

    code = run_cli(
        ["jobs", "digest", "--out", str(tmp_path / "fuera.txt")],
        standalone_mode=False,
    )
    assert code == VALIDATION_FAILURE
    assert not (tmp_path / "fuera.txt").exists()
