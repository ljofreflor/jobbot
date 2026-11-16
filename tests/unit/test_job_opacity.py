"""Employer-side opacity is local evidence. Fit stays; closed postings rank last."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from jobbot.exit_codes import SUCCESS
from jobbot.jobs import opacity
from jobbot.jobs.opacity import assess, band_for, opacity_score, shortlist_key
from jobbot.models.job import JobPosting

NOW = datetime(2026, 10, 18, 12, 0, tzinfo=UTC)


def _job(job_id: str, **overrides: object) -> JobPosting:
    data: dict[str, object] = {
        "id": job_id,
        "source": "manual",
        "title": "Analyst",
        "company": "Estudio Neutro",
        "description": "Una descripcion de un aviso. " * 8,
        "posted_at": NOW - timedelta(days=2),
    }
    data.update(overrides)
    return JobPosting.model_validate(data)


def test_caduco_banner_is_closed_and_ranks_last() -> None:
    closed = _job("J0002", description="El aviso dice: este empleo caducó.")
    assert assess(
        closed, peers=[closed], sites=[], events=[], now=NOW
    ).closure == "closed"
    open_key = shortlist_key(closed=False, band="murky", fit=10)
    closed_key = shortlist_key(closed=True, band="clear", fit=90)
    assert open_key < closed_key


def test_published_close_already_past_is_closed() -> None:
    expired = _job("J0003", closes_on=(NOW - timedelta(days=2)).date())
    ahead = _job("J0004", closes_on=(NOW + timedelta(days=30)).date())
    assert assess(expired, peers=[expired], sites=[], events=[], now=NOW).closure == "closed"
    assert assess(ahead, peers=[ahead], sites=[], events=[], now=NOW).closure == "unknown"


def test_same_ats_url_marks_both_ids_as_reposts() -> None:
    url = "https://boards.greenhouse.io/acme/jobs/1?utm_source=x"
    first = _job("J0001", ats_url=url, title="Uno")
    second = _job("J0002", ats_url=url + "&ref=2", title="Dos", company="Otra")
    peers = [first, second]
    for job in peers:
        signal = assess(job, peers=peers, sites=[], events=[], now=NOW)
        assert signal.repost is True


def test_evidenced_greenhouse_host_is_a_known_portal() -> None:
    job = _job("J0001", url="https://boards.greenhouse.io/acme/jobs/9")
    known = assess(
        job,
        peers=[job],
        sites=[("boards.greenhouse.io", "greenhouse")],
        events=[],
        now=NOW,
    )
    unknown = assess(
        job,
        peers=[job],
        sites=[("boards.greenhouse.io", "unknown")],
        events=[],
        now=NOW,
    )
    assert known.portal_known is True
    assert unknown.portal_known is False


def test_prepared_event_past_the_window_is_silence() -> None:
    job = _job("J0001")
    events = [("status", "prepared", NOW - timedelta(days=40))]
    silent = assess(job, peers=[job], sites=[], events=events, now=NOW, silence_days=30)
    recent = [("status", "prepared", NOW - timedelta(days=10))]
    quiet = assess(job, peers=[job], sites=[], events=recent, now=NOW, silence_days=30)
    moved = [
        ("status", "prepared", NOW - timedelta(days=40)),
        ("status", "interview", NOW - timedelta(days=1)),
    ]
    later = assess(job, peers=[job], sites=[], events=moved, now=NOW, silence_days=30)
    assert silent.silence == "silent"
    assert quiet.silence == "n/a"
    assert later.silence == "n/a"


def test_opacity_score_is_a_pure_function_of_the_weights() -> None:
    clear = opacity_score(freshness="fresh", repost=False, portal_known=True, silence="n/a")
    murky = opacity_score(freshness="stale", repost=False, portal_known=False, silence="n/a")
    opaque = opacity_score(freshness="stale", repost=True, portal_known=False, silence="silent")
    assert clear == 0.0
    assert band_for(clear) == "clear"
    assert murky == 0.50
    assert band_for(murky) == "murky"
    assert opaque == 1.0
    assert band_for(opaque) == "opaque"
    assert "urlopen" not in Path(opacity.__file__).read_text(encoding="utf-8")


def test_shortlist_prints_the_band_and_ranks_the_banner_last(
    tmp_path: Path, monkeypatch, project_root: Path, capsys
) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "profile.yaml").write_text(
        (project_root / "data" / "profile.example.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("jobbot.jobs.closing.utc_now", lambda: NOW)

    from jobbot.cli import load_config, run_cli
    from jobbot.db.engine import make_engine, make_session_factory
    from jobbot.jobs.repository import JobRepository

    config = load_config()
    session = make_session_factory(make_engine(config.database_path))()
    repo = JobRepository(session)
    repo.save(_job("J0001"))
    repo.save(_job("J0002", description="El aviso dice: este empleo caducó."))

    assert run_cli(["jobs", "shortlist"], standalone_mode=False) == SUCCESS
    out = capsys.readouterr().out
    assert out.index("J0001") < out.index("J0002")
    assert "opacity" in out
    assert "closed" in out.split("J0002", 1)[1]
