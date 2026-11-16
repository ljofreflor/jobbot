"""Profile consistency status across local / Indeed / LinkedIn snapshots."""

from __future__ import annotations

from typing import Any

from jobbot.adapters.diff_engine import load_snapshot, snapshot_unread
from jobbot.config import JobbotConfig
from jobbot.profile.loader import load_profile


def build_profile_status(config: JobbotConfig) -> dict[str, Any]:
    candidate = load_profile(config.profile_path)
    indeed = load_snapshot(config.output_dir, "indeed")
    linkedin = load_snapshot(config.output_dir, "linkedin")

    def mark(local: str | None, remote: str | None) -> str:
        if remote is None:
            return "—"
        if not local and not remote:
            return "—"
        if (local or "").strip() == (remote or "").strip():
            return "✓"
        return "!"

    linkedin_unread = linkedin is not None and snapshot_unread(linkedin)

    def linkedin_mark(present: bool, remote: str | None = None) -> str:
        if linkedin is None:
            return "—"
        if linkedin_unread:
            return "no leído"
        if remote is not None:
            return mark(candidate.personal.headline, remote)
        return "✓" if present else "!"

    rows = [
        {
            "section": "Headline",
            "local": "✓",
            "indeed": mark(candidate.personal.headline, indeed.headline if indeed else None),
            "linkedin": linkedin_mark(False, linkedin.headline if linkedin else None),
        },
        {
            "section": "Experience",
            "local": "✓",
            "indeed": (
                "✓"
                if indeed and indeed.experience
                else ("—" if indeed is None else "!")
            ),
            "linkedin": linkedin_mark(bool(linkedin and linkedin.experience)),
        },
        {
            "section": "Skills",
            "local": "✓",
            "indeed": (
                "✓"
                if indeed and indeed.skills
                else ("—" if indeed is None else "!")
            ),
            "linkedin": linkedin_mark(bool(linkedin and linkedin.skills)),
        },
    ]
    return {"rows": rows}
