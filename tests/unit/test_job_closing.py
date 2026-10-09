"""Closing date, time and zone as a posting publishes them — never guessed (#215, #205)."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from jobbot.jobs.closing import (
    ClosingState,
    closing_state,
    describe_closing,
    find_closing,
    parse_closing_value,
)

SANTIAGO = ZoneInfo("America/Santiago")


def test_label_and_value_on_separate_lines_like_workday_html() -> None:
    text = (
        "Job Posting:\nseptiembre 17, 2026\nClosing Date:\noctubre 11, 2026, 11:59 PM Eastern Time"
    )

    found = find_closing(text)

    assert found is not None
    assert found.on == date(2026, 10, 11)
    assert found.at == datetime(2026, 10, 11, 23, 59, tzinfo=ZoneInfo("America/New_York"))
    assert "Eastern Time" in found.text


@pytest.mark.parametrize(
    ("value", "local"),
    [
        # Washington in UTC-4 (EDT), Santiago in UTC-3: one hour later, next day.
        ("October 15, 2026, 23:59 Washington DC time", datetime(2026, 10, 16, 0, 59)),
        # From November Washington is UTC-5: two hours later.
        ("November 15, 2026, 11:59 PM (Washington, D.C. time)", datetime(2026, 11, 16, 1, 59)),
    ],
)
def test_washington_close_lands_on_the_next_day_in_chile(value: str, local: datetime) -> None:
    found = parse_closing_value(value)

    assert found is not None and found.at is not None
    assert found.at.astimezone(SANTIAGO).replace(tzinfo=None) == local


def test_ambiguous_zone_keeps_the_date_and_no_moment() -> None:
    """'Central Time' fits two countries with different DST: no hour is invented."""
    found = parse_closing_value("octubre 12, 2026, 11:59 PM Central Time")

    assert found is not None
    assert found.on == date(2026, 10, 12)
    assert found.at is None


def test_date_without_time_keeps_no_moment() -> None:
    found = find_closing("Fecha de cierre: 20 de octubre de 2026")

    assert found is not None
    assert found.on == date(2026, 10, 20)
    assert found.at is None


def test_explicit_offset_and_fixed_standard_time() -> None:
    offset = parse_closing_value("2026-10-20 17:00 GMT-4")
    atlantic = parse_closing_value("October 27, 2026, 11:59 PM Atlantic Standard Time")

    assert offset is not None and offset.at is not None
    assert offset.at.utcoffset() == timedelta(hours=-4)
    assert atlantic is not None and atlantic.at is not None
    assert atlantic.at.utcoffset() == timedelta(hours=-4)


def test_numeric_day_month_dates_are_not_guessed() -> None:
    assert find_closing("Deadline: 10/11/2026") is None
    assert find_closing("No closing line here") is None


def test_state_uses_the_exact_moment_when_known() -> None:
    closes = datetime(2026, 10, 11, 23, 59, tzinfo=ZoneInfo("America/New_York"))

    assert closing_state(closes, None, now=closes + timedelta(minutes=1)) is ClosingState.EXPIRED
    assert closing_state(closes, None, now=closes - timedelta(days=1)) is ClosingState.SOON
    assert closing_state(closes, None, now=closes - timedelta(days=9)) is ClosingState.OPEN


def test_bare_date_is_expired_only_once_it_ended_everywhere() -> None:
    day = date(2026, 10, 9)
    late_evening_utc = datetime(2026, 10, 9, 23, 0, tzinfo=UTC)
    two_days_later = datetime(2026, 10, 11, 0, 0, tzinfo=UTC)

    assert closing_state(None, day, now=late_evening_utc) is ClosingState.SOON
    assert closing_state(None, day, now=two_days_later) is ClosingState.EXPIRED
    assert closing_state(None, None, now=two_days_later) is None


def test_describe_shows_the_posting_clock_and_the_local_one() -> None:
    closes = datetime(2026, 10, 15, 23, 59, tzinfo=ZoneInfo("America/New_York"))

    line = describe_closing(closes, None, local_tz=SANTIAGO)

    assert line == "2026-10-15 23:59 (UTC-04:00) → 2026-10-16 00:59 hora local"
    assert describe_closing(None, date(2026, 10, 9)) == "2026-10-09 (hora no publicada)"
    assert describe_closing(None, None) == "—"
    assert "UTC+05:30" in describe_closing(
        datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=5, minutes=30))), None
    )
