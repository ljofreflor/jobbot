"""SQLite job repository tests."""

from __future__ import annotations

from pathlib import Path

from jobbot.db.engine import make_engine, make_session_factory
from jobbot.jobs.repository import JobRepository


def test_add_and_get_job(tmp_path: Path) -> None:
    engine = make_engine(tmp_path / "test.sqlite")
    session = make_session_factory(engine)()
    repo = JobRepository(session)
    text = Path("tests/fixtures/jobs/senior_ds_retail.txt").read_text(encoding="utf-8")
    job = repo.add_from_text(text)
    assert job.id == "J0001"
    loaded = repo.get("J0001")
    assert loaded is not None
    assert loaded.company == "Sodimac"
    job2 = repo.add_from_text(text)
    assert job2.id == "J0002"
