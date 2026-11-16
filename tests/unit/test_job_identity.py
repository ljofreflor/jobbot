"""Public job identity: fixed share code, URL history, no slug merging."""

from __future__ import annotations

from pathlib import Path

import pytest

from jobbot.db.engine import make_engine, make_session_factory
from jobbot.jobs.discover import unique_jobs
from jobbot.jobs.identity import (
    SHARE_CODE_LENGTH,
    canonical_job_key,
    share_code_for_key,
    share_code_for_url,
)
from jobbot.jobs.repository import JobRepository, StoredJobIndex
from jobbot.models.job import JobPosting


def _repo(tmp_path: Path) -> JobRepository:
    engine = make_engine(tmp_path / "jobs.sqlite")
    return JobRepository(make_session_factory(engine)())


def _job(url: str, *, source_job_id: str | None = None) -> JobPosting:
    return JobPosting(
        id="PENDING",
        title="Analyst",
        company="Northwind",
        url=url,
        description="A public opening.",
        source_job_id=source_job_id,
    )


def test_share_code_length_is_fixed() -> None:
    code = share_code_for_key("careers.example.com/jobs/42")
    assert len(code) == SHARE_CODE_LENGTH == 12
    assert code == share_code_for_key("careers.example.com/jobs/42")


def test_mailto_has_no_share_code() -> None:
    assert canonical_job_key("mailto:ada@example.com") is None
    assert share_code_for_url("mailto:ada@example.com") is None


def test_tracking_query_is_the_same_job_and_is_not_stored(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    clean = "https://boards.example.com/jobs/42"
    tracked = f"{clean}?utm_source=share&rcm=member-id"
    first = repo.upsert_external(_job(clean))
    second = repo.upsert_external(_job(tracked))

    assert second.id == first.id
    assert second.share_code == first.share_code
    assert second.share_code is not None
    assert len(second.share_code) == SHARE_CODE_LENGTH
    assert "rcm=" not in (second.url or "")
    assert "utm_" not in (second.url or "")
    seen = " ".join(repo.urls_for(first.id))
    assert clean in seen
    assert "member-id" not in seen
    assert "utm_" not in seen


def test_a_different_slug_is_a_different_job(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    first = repo.upsert_external(
        _job("https://careers.example.com/job/1/role-a", source_job_id="same-external")
    )
    second = repo.upsert_external(
        _job("https://careers.example.com/job/1/role-b", source_job_id="same-external")
    )

    assert first.id != second.id
    assert first.share_code != second.share_code
    assert "role-b" not in " ".join(repo.urls_for(first.id))
    assert "role-a" not in " ".join(repo.urls_for(second.id))


def test_indeed_job_key_is_not_dropped(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    first = repo.upsert_external(_job("https://cl.indeed.com/viewjob?jk=aaa"))
    second = repo.upsert_external(_job("https://cl.indeed.com/viewjob?jk=bbb&utm_source=share"))

    assert first.id != second.id
    assert "jk=bbb" in (second.url or "")
    assert "utm_" not in (second.url or "")


def test_mailto_stays_a_local_row(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    first = repo.upsert_external(_job("mailto:ada@example.com"))
    again = repo.upsert_external(_job("mailto:ada@example.com"))
    other = repo.upsert_external(_job("mailto:bea@example.com"))

    assert first.share_code is None
    assert again.id == first.id
    assert other.id != first.id
    assert repo.urls_for(first.id) == []


def test_same_code_on_two_urls_is_kept_not_lengthened(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import jobbot.jobs.repository as repository

    monkeypatch.setattr(repository, "share_code_for_key", lambda _key: "a" * SHARE_CODE_LENGTH)
    repo = _repo(tmp_path)
    first = repo.upsert_external(_job("https://careers.example.com/jobs/1"))
    second = repo.upsert_external(_job("https://careers.example.com/jobs/2"))

    assert first.share_code == "a" * SHARE_CODE_LENGTH
    assert second.share_code == first.share_code
    assert len(second.share_code or "") == SHARE_CODE_LENGTH
    found = repo.find_by_share_code("a" * SHARE_CODE_LENGTH)
    assert {job.id for job in found} == {first.id, second.id}


def test_add_from_text_refreshes_body_when_url_matches(tmp_path: Path) -> None:
    repo = _repo(tmp_path)
    url = "https://boards.example.com/jobs/42"
    first = repo.add_from_text("Old title\n\nOld body about Northwind.", url=url)
    again = repo.add_from_text(
        "Fresh title\nCompany: Acme\n\nNew description for the same vacancy.",
        url=f"{url}?utm_source=share",
    )

    assert again.id == first.id
    loaded = repo.get(first.id)
    assert loaded is not None
    assert "New description" in loaded.description
    assert "Old body" not in loaded.description


def test_discover_preview_matches_canonical_url() -> None:
    clean = "https://boards.example.com/jobs/42"
    index = StoredJobIndex([("J0001", "manual", None, clean)])
    tracked = JobPosting(
        id="PENDING",
        title="Analyst",
        company="Northwind",
        url=f"{clean}?utm_source=li&rcm=member",
        description="A public opening.",
    )
    other = JobPosting(
        id="PENDING",
        title="Other",
        company="Northwind",
        url="https://boards.example.com/jobs/99",
        description="Another opening.",
    )
    assert index.lookup(tracked) == "J0001"
    assert index.lookup(other) is None


def test_discover_preview_splits_same_source_id_on_different_paths() -> None:
    index = StoredJobIndex(
        [
            (
                "J0001",
                "greenhouse",
                "same-external",
                "https://careers.example.com/job/1/role-a",
            )
        ]
    )
    sibling = JobPosting(
        id="PENDING",
        title="Role B",
        company="Northwind",
        url="https://careers.example.com/job/1/role-b",
        description="A different slug.",
        source="greenhouse",
        source_job_id="same-external",
    )
    assert index.lookup(sibling) is None


def test_unique_jobs_collapses_tracking_variants() -> None:
    clean = "https://boards.example.com/jobs/42"
    first = JobPosting(
        id="PENDING",
        title="Analyst",
        company="Northwind",
        url=clean,
        description="A public opening.",
        source_job_id="ext-1",
    )
    tracked = JobPosting(
        id="PENDING",
        title="Analyst",
        company="Northwind",
        url=f"{clean}?utm_campaign=x",
        description="A public opening.",
        source_job_id="ext-1",
    )
    kept = unique_jobs([first, tracked])
    assert len(kept) == 1
    assert kept[0].url == clean
