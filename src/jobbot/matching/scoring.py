"""Scoring helpers (kept thin; core logic in analyzer)."""

from collections.abc import Sequence

from jobbot.models.match import JobMatch, MatchItem, MatchStrength

_BLIND_MIN_JOBS = 2
# Below this every score is noise: one partial word out of a page of requirements.
_BLIND_MAX_SCORE = 5.0
_REASON_LABEL_CHARS = 60
_MARKS = {
    MatchStrength.STRONG: "✓",
    MatchStrength.PARTIAL: "~",
    MatchStrength.MISSING: "✗",
    MatchStrength.UNKNOWN: "?",
}


def blind_matcher_warning(scores: Sequence[float]) -> str | None:
    """Every job at (about) 0% says more about the matcher than about the candidate.

    A real search always turns up something partly related; when nothing scores at
    all, the matcher could not read this profile against these postings (language,
    vocabulary, page noise), and a ranked list of zeros would read as 'nothing fits'.
    """
    if len(scores) < _BLIND_MIN_JOBS or any(score >= _BLIND_MAX_SCORE for score in scores):
        return None
    ceiling = "0%" if not any(scores) else f"under {_BLIND_MAX_SCORE:.0f}%"
    return (
        f"Matcher alert: all {len(scores)} jobs scored {ceiling}. That usually means the "
        "matcher could not read this profile against these postings, not that nothing fits. "
        "Open one with `jobbot jobs match Jxxxx` before discarding them."
    )


def match_reasons(match: JobMatch, limit: int = 3) -> list[str]:
    """Why a job ranks where it does: role fit, the strongest evidence, the first gap.

    A bare percentage hides an inflated score (a teaching post ranked first on the
    words of a headline), so the shortlist prints these next to it.
    """
    role = next((item for item in match.items if item.label.startswith("role:")), None)
    strong = [
        item for item in match.items if item.strength == MatchStrength.STRONG and item is not role
    ]
    missing = [
        item for item in match.items if item.strength == MatchStrength.MISSING and item is not role
    ]
    reasons: list[str] = []
    if role is not None:
        reasons.append(f"{_MARKS[role.strength]} role: {role.detail}")
    room = limit - len(reasons) - (1 if missing else 0)
    reasons += [_reason(item) for item in strong[: max(room, 0)]]
    if missing and len(reasons) < limit:
        reasons.append(_reason(missing[0]))
    return reasons[:limit]


def _reason(item: MatchItem) -> str:
    label = item.label
    if len(label) > _REASON_LABEL_CHARS:
        label = label[: _REASON_LABEL_CHARS - 1].rstrip() + "…"
    return f"{_MARKS[item.strength]} {label}"


def format_match_report(match: JobMatch) -> str:
    lines = [f"MATCH: {match.score:.0f}%"]
    groups = [
        ("Strong", "strong_match", "✓"),
        ("Partial", "partial_match", "~"),
        ("Missing", "missing", "✗"),
        ("Unknown", "unknown", "?"),
    ]
    data = match.to_dict()
    for title, key, mark in groups:
        values = data[key]
        assert isinstance(values, list)
        if not values:
            continue
        lines.append(title)
        for label in values:
            lines.append(f"{mark} {label}")
    return "\n".join(lines)
