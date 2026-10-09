"""When a posting stops taking applications, read from what it publishes — or nothing.

A closing line reads like ``Closing Date: October 16, 2026, 11:59 PM Eastern Time``.
The date is kept whenever it parses. The exact moment (`at`) needs both a time and a
zone that names one place's clock: "Central Time" fits two countries with different
DST rules, so it stays unknown instead of guessed. Numeric dates other than ISO
(``10/11/2026``) are skipped for the same reason: day and month cannot be told apart.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, timezone, tzinfo
from enum import StrEnum
from functools import cache
from zoneinfo import ZoneInfo

from babel.dates import get_month_names

_LOCALES = ("en", "es", "fr", "pt")

_LABEL = re.compile(
    r"\b(?:closing date|application deadline|deadline for applications|deadline|"
    r"apply by|applications close|fecha de cierre|fecha limite|cierre de postulaciones|"
    r"date de cloture|date limite|data de encerramento|data limite)\b\s*:?\s*"
)
_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})\b")
_DAY_MONTH_YEAR = re.compile(r"^(\d{1,2})\s+(?:de\s+)?([a-z]+)\s+(?:de\s+)?(\d{4})\b")
_MONTH_DAY_YEAR = re.compile(r"^([a-z]+)\s+(\d{1,2})\s+(\d{4})\b")
_TIME = re.compile(r"^(?:at\s+|a las\s+)?(\d{1,2})[:h](\d{2})\s*(am|pm|a m|p m)?\b")
_OFFSET = re.compile(r"^(?:gmt|utc)\s*([+-])\s*(\d{1,2})(?::?(\d{2}))?\b")

# Zone names that point at exactly one clock. Folded: lowercase, no accents/punctuation.
_ZONES: dict[str, str] = {
    "eastern time": "America/New_York",
    "us eastern time": "America/New_York",
    "washington dc time": "America/New_York",
    "washington d c time": "America/New_York",
    "new york time": "America/New_York",
    "pacific time": "America/Los_Angeles",
    "atlantic standard time": "UTC-04:00",
    "venezuela time": "America/Caracas",
    "peru standard time": "America/Lima",
    "peru time": "America/Lima",
    "colombia standard time": "America/Bogota",
    "colombia time": "America/Bogota",
    "brasilia standard time": "America/Sao_Paulo",
    "brasilia time": "America/Sao_Paulo",
    "chile time": "America/Santiago",
    "chile standard time": "America/Santiago",
    "hora de chile": "America/Santiago",
    "argentina time": "America/Argentina/Buenos_Aires",
    "central european time": "Europe/Paris",
    "cet": "Europe/Paris",
    "geneva time": "Europe/Zurich",
    "gmt": "UTC",
    "utc": "UTC",
    "coordinated universal time": "UTC",
}

SOON_DAYS = 3


class ClosingState(StrEnum):
    EXPIRED = "expired"
    SOON = "soon"
    OPEN = "open"


def utc_now() -> datetime:
    """The clock every closing decision reads (one seam, so tests can pin it)."""
    return datetime.now(UTC)


@dataclass(frozen=True)
class Closing:
    on: date
    at: datetime | None
    text: str


def _fold(text: str) -> str:
    stripped = unicodedata.normalize("NFKD", text or "")
    plain = "".join(ch for ch in stripped if not unicodedata.combining(ch)).casefold()
    plain = re.sub(r"[^\w:+\-]+", " ", plain)
    return re.sub(r"\s+", " ", plain).strip()


@cache
def _months() -> dict[str, int]:
    names: dict[str, int] = {}
    for locale in _LOCALES:
        for width in ("wide", "abbreviated"):
            for number, name in get_month_names(width, locale=locale).items():
                names.setdefault(_fold(str(name)), int(number))
    return names


def _zone(name: str) -> tzinfo:
    if name.startswith("UTC-") or name.startswith("UTC+"):
        sign = -1 if name[3] == "-" else 1
        hours, minutes = name[4:].split(":")
        return timezone(sign * timedelta(hours=int(hours), minutes=int(minutes)))
    return UTC if name == "UTC" else ZoneInfo(name)


def _date(value: str) -> tuple[date, str] | None:
    months = _months()
    try:
        if found := _ISO.match(value):
            year, month, day = (int(g) for g in found.groups())
            return date(year, month, day), value[found.end() :].strip()
        if found := _DAY_MONTH_YEAR.match(value):
            named = months.get(found.group(2))
            if named:
                when = date(int(found.group(3)), named, int(found.group(1)))
                return when, value[found.end() :].strip()
        if found := _MONTH_DAY_YEAR.match(value):
            named = months.get(found.group(1))
            if named:
                when = date(int(found.group(3)), named, int(found.group(2)))
                return when, value[found.end() :].strip()
    except ValueError:
        return None
    return None


def _time(value: str) -> tuple[time, str] | None:
    found = _TIME.match(value)
    if found is None:
        return None
    hour, minute = int(found.group(1)), int(found.group(2))
    meridiem = (found.group(3) or "").replace(" ", "")
    if meridiem == "pm" and hour < 12:
        hour += 12
    elif meridiem == "am" and hour == 12:
        hour = 0
    if hour > 23 or minute > 59:
        return None
    return time(hour, minute), value[found.end() :].strip()


def zone_from_text(value: str) -> tzinfo | None:
    """The zone a folded tail names, or None when it names none (or several)."""
    if found := _OFFSET.match(value):
        sign = -1 if found.group(1) == "-" else 1
        delta = timedelta(hours=int(found.group(2)), minutes=int(found.group(3) or 0))
        return timezone(sign * delta)
    for key in sorted(_ZONES, key=len, reverse=True):
        if value == key or value.startswith(key + " "):
            return _zone(_ZONES[key])
    return None


def parse_closing_value(value: str, *, evidence: str | None = None) -> Closing | None:
    """``October 16, 2026, 11:59 PM Eastern Time`` → date, and moment when knowable."""
    folded = _fold(value)
    parsed = _date(folded)
    if parsed is None:
        return None
    on, rest = parsed
    at: datetime | None = None
    clock = _time(rest)
    if clock is not None:
        moment, tail = clock
        zone = zone_from_text(tail)
        if zone is not None:
            at = datetime.combine(on, moment, tzinfo=zone)
    return Closing(on=on, at=at, text=(evidence or value).strip()[:160])


def find_closing(text: str) -> Closing | None:
    """First labelled closing line in a posting (label and value may sit on two lines)."""
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    for index, line in enumerate(lines):
        label = _LABEL.search(_fold(line))
        if label is None:
            continue
        value = _fold(line)[label.end() :].strip()
        evidence = line
        if not value and index + 1 < len(lines):
            value = lines[index + 1]
            evidence = f"{line} {lines[index + 1]}"
        found = parse_closing_value(value, evidence=evidence)
        if found is not None:
            return found
    return None


def closing_state(
    closes_at: datetime | None,
    closes_on: date | None,
    *,
    now: datetime,
    soon_days: int = SOON_DAYS,
) -> ClosingState | None:
    """Expired / closing soon / open. A bare date is judged by its latest possible end."""
    window = timedelta(days=soon_days)
    if closes_at is not None:
        end = closes_at
    elif closes_on is not None:
        # The last place on Earth to finish that date is UTC-12.
        end = datetime.combine(closes_on, time(23, 59), tzinfo=timezone(timedelta(hours=-12)))
    else:
        return None
    if end <= now:
        return ClosingState.EXPIRED
    if end - now <= window:
        return ClosingState.SOON
    return ClosingState.OPEN


def describe_closing(
    closes_at: datetime | None,
    closes_on: date | None,
    *,
    local_tz: tzinfo | None = None,
) -> str:
    """One line for humans: the posting's own clock, then the local one."""
    if closes_at is not None:
        own = closes_at.strftime("%Y-%m-%d %H:%M") + f" ({_offset_label(closes_at)})"
        if local_tz is None:
            return own
        local = closes_at.astimezone(local_tz)
        return f"{own} → {local.strftime('%Y-%m-%d %H:%M')} hora local"
    if closes_on is not None:
        return f"{closes_on.isoformat()} (hora no publicada)"
    return "—"


def _offset_label(moment: datetime) -> str:
    offset = moment.utcoffset() or timedelta(0)
    minutes = int(offset.total_seconds() // 60)
    sign = "-" if minutes < 0 else "+"
    minutes = abs(minutes)
    return f"UTC{sign}{minutes // 60:02d}:{minutes % 60:02d}"
