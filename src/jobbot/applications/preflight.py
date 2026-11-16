"""Warn before an assisted apply when the stored match is below a threshold.

The check never invents a fact to raise the score. A dry-run does not ask.
``0.7`` and ``70`` are the same bar.
"""

from __future__ import annotations

DEFAULT_MIN_MATCH = 70.0


class MatchThresholdError(ValueError):
    """``--min-match`` is outside 0–100. Not an ops defect."""


def threshold_percent(value: float) -> float:
    """A fraction up to 1 is a percent. ``0.7`` is 70. Above 100 is refused."""
    percent = round(value * 100, 4) if 0 <= value <= 1 else value
    if percent < 0 or percent > 100:
        msg = "--min-match must be between 0 and 100 (0.7 means 70%)"
        raise MatchThresholdError(msg)
    return percent


def below_threshold(score: float | None, minimum: float) -> bool:
    """Missing scores do not block. A stored score under the bar does."""
    return score is not None and score < minimum
