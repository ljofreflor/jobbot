"""Shortlist expired / urgent flags without inventing a close date (#205)."""

from __future__ import annotations

from datetime import date

from jobbot.jobs.shortlist_flags import parse_closes_on, shortlist_flags
from jobbot.models.job import JobPosting


def _job(description: str, *, raw: str = "") -> JobPosting:
    return JobPosting(
        id="J0001",
        title="Analyst",
        company="Example Org",
        description=description,
        raw_description=raw,
    )


def test_filled_phrase_marks_expired() -> None:
    flags = shortlist_flags(
        _job("This position has been filled. Requirements: Python."),
        today=date(2026, 10, 6),
    )
    assert "expired" in flags.labels
    assert flags.expired is not None
    assert "filled" in flags.expired.casefold()
    assert "urgent" not in flags.labels


def test_past_iso_deadline_marks_expired() -> None:
    flags = shortlist_flags(
        _job("Apply now. Deadline: 2026-09-01\nRequirements: SQL"),
        today=date(2026, 10, 6),
    )
    assert flags.labels == ("expired",)
    assert flags.expired == "deadline passed: 2026-09-01"


def test_near_deadline_marks_urgent() -> None:
    flags = shortlist_flags(
        _job("Closes: 2026-10-10\nRequirements: Python"),
        today=date(2026, 10, 6),
        urgent_days=7,
    )
    assert flags.labels == ("urgent",)
    assert flags.urgent == "closes 2026-10-10"


def test_far_deadline_is_silent() -> None:
    flags = shortlist_flags(
        _job("Closing date 2026-12-01"),
        today=date(2026, 10, 6),
        urgent_days=7,
    )
    assert flags.labels == ()
    assert flags.expired is None
    assert flags.urgent is None


def test_relative_or_ambiguous_date_is_not_invented() -> None:
    assert parse_closes_on("Closes in 3 days") is None
    assert parse_closes_on("Deadline: tomorrow") is None
    assert parse_closes_on("Cierre: 10/06/2026") is None  # day-first, ambiguous
    flags = shortlist_flags(
        _job("Closes in 3 days. Apply ASAP."),
        today=date(2026, 10, 6),
    )
    assert flags.labels == ()


def test_spanish_hasta_iso_parses() -> None:
    assert parse_closes_on("Postula hasta 2026-10-08") == date(2026, 10, 8)


def test_expired_wins_over_urgent_when_both() -> None:
    flags = shortlist_flags(
        _job(
            "This job has expired.\nDeadline: 2026-10-07",
        ),
        today=date(2026, 10, 6),
        urgent_days=7,
    )
    assert flags.labels == ("expired",)
    assert "urgent" not in flags.labels
