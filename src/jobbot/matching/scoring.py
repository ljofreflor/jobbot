"""Scoring helpers (kept thin; core logic in analyzer)."""

from jobbot.models.match import JobMatch


def format_match_report(match: JobMatch) -> str:
    lines = [f"MATCH: {match.score:.0f}%"]
    if match.document_score is not None and match.lexical_score is not None:
        lines.append(
            f"  (lexical {match.lexical_score:.0f}% · "
            f"document/{match.fit_mode} {match.document_score:.0f}%)"
        )
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
