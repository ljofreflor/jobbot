"""Indeed job search HTML parsing tests."""

from __future__ import annotations

from pathlib import Path

from jobbot.adapters.indeed.jobs import (
    card_to_job_posting,
    parse_indeed_job_detail_html,
    parse_indeed_search_html,
)
from jobbot.db.engine import make_engine, make_session_factory
from jobbot.jobs.repository import JobRepository


def test_parse_indeed_search_fixture(project_root: Path) -> None:
    html = (project_root / "tests/fixtures/indeed_search.html").read_text(encoding="utf-8")
    cards = parse_indeed_search_html(html, base_url="https://cl.indeed.com")
    assert len(cards) == 2
    assert cards[0]["source_job_id"] == "abc123def456"
    assert cards[0]["title"] == "Senior Data Scientist"
    assert cards[0]["company"] == "Sodimac"
    assert "jk=abc123def456" in (cards[0]["url"] or "")


def test_parse_live_indeed_card_shape_extracts_title(project_root: Path) -> None:
    """Regression: Untitled when window started at data-jk mid-<a> (cl.indeed 2026)."""
    html = (project_root / "tests/fixtures/indeed_search_live_cards.html").read_text(
        encoding="utf-8"
    )
    cards = parse_indeed_search_html(html, base_url="https://cl.indeed.com")
    assert len(cards) == 2
    assert cards[0]["title"] == "Data Scientist Senior"
    assert cards[0]["company"] == "Levi Strauss & Co."
    assert cards[0]["location"] == "Las Condes, Región Metropolitana"
    assert cards[1]["title"] == "Senior Data Scientist, DTC"
    assert cards[1]["company"] == "pfsGROUP"


def test_parse_indeed_detail_fixture(project_root: Path) -> None:
    html = (project_root / "tests/fixtures/indeed_job_detail.html").read_text(encoding="utf-8")
    detail = parse_indeed_job_detail_html(html)
    assert detail["title"] == "Senior Data Scientist"
    assert detail["company"] == "Sodimac"
    assert "Python" in (detail["description"] or "")


def test_card_to_job_and_upsert_dedupes(project_root: Path, tmp_path: Path) -> None:
    html = (project_root / "tests/fixtures/indeed_search.html").read_text(encoding="utf-8")
    detail = (project_root / "tests/fixtures/indeed_job_detail.html").read_text(encoding="utf-8")
    cards = parse_indeed_search_html(html, base_url="https://cl.indeed.com")
    job = card_to_job_posting(cards[0], detail_html=detail, placeholder_id="TMP")
    assert job.source == "indeed"
    assert job.source_job_id == "abc123def456"
    assert "Python" in job.skills or "python" in job.description.lower()

    engine = make_engine(tmp_path / "t.sqlite")
    session = make_session_factory(engine)()
    repo = JobRepository(session)
    a = repo.upsert_external(job)
    b = repo.upsert_external(job)
    assert a.id == b.id
    assert a.id.startswith("J")
    assert len(repo.list_all()) == 1
