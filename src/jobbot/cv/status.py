"""Permanent CV / profile presence across local artifacts and portals.

Evidence only: a destination is never reported as uploaded without a local
receipt or snapshot. ``jobbot status`` is a read-only view; writes stay in
``cv build``, ``cv propagate``, and portal ``--apply`` commands.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from jobbot.adapters.getonboard.cv_upload import (
    load_upload_receipt,
    resolve_base_cv,
)
from jobbot.adapters.getonboard.draft import (
    load_permanent_profile,
    permanent_profile_md_path,
)
from jobbot.config import JobbotConfig
from jobbot.cv.propagate import plan_getonboard, plan_indeed, plan_linkedin
from jobbot.models.candidate import Candidate


class PresenceState(StrEnum):
    """What we can claim from local evidence alone."""

    MISSING = "missing"
    PRESENT = "present"
    UNKNOWN = "unknown"
    IN_SYNC = "in_sync"
    STALE = "stale"
    BLOCKED = "blocked"
    BEHIND = "behind"
    OK = "ok"
    PENDING = "pending"


@dataclass(frozen=True)
class PresenceRow:
    """One destination in the status table."""

    destination: str
    artifact: str
    state: PresenceState
    evidence: str
    hint: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "destination": self.destination,
            "artifact": self.artifact,
            "state": self.state.value,
            "evidence": self.evidence,
            "hint": self.hint,
        }


@dataclass(frozen=True)
class CvStatusReport:
    """All permanent destinations JobBot maintains."""

    rows: list[PresenceRow]

    def to_dict(self) -> dict[str, Any]:
        return {"rows": [row.to_dict() for row in self.rows]}


def build_cv_status(config: JobbotConfig, candidate: Candidate) -> CvStatusReport:
    """Assemble presence rows without writing files or opening a browser."""
    rows = [
        _local_pdf(config),
        _getonboard_cv(config),
        _getonboard_profile(config, candidate),
        _indeed(config, candidate),
        _linkedin(config, candidate),
    ]
    return CvStatusReport(rows=rows)


def _local_pdf(config: JobbotConfig) -> PresenceRow:
    path = resolve_base_cv(config.output_dir)
    if not path.is_file():
        return PresenceRow(
            destination="local",
            artifact=str(path.as_posix()),
            state=PresenceState.MISSING,
            evidence="no PDF yet",
            hint="jobbot cv build",
        )
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    mtime = datetime.fromtimestamp(path.stat().st_mtime).date().isoformat()
    return PresenceRow(
        destination="local",
        artifact=str(path.as_posix()),
        state=PresenceState.PRESENT,
        evidence=f"{mtime} · sha256 {digest[:12]}…",
    )


def _getonboard_cv(config: JobbotConfig) -> PresenceRow:
    receipt = load_upload_receipt(config.output_dir)
    path = resolve_base_cv(config.output_dir)
    if receipt is None:
        return PresenceRow(
            destination="getonboard",
            artifact="Tus CVs",
            state=PresenceState.UNKNOWN,
            evidence="no upload receipt — not recorded locally",
            hint="jobbot getonboard upload-cv --apply",
        )
    label = receipt.label
    default = "default" if receipt.is_default else "not default"
    when = receipt.uploaded_at.date().isoformat() if receipt.uploaded_at else "—"
    evidence = f"label={label} · {default} · {when} · sha256 {receipt.sha256[:12]}…"
    if path.is_file():
        current = hashlib.sha256(path.read_bytes()).hexdigest()
        if current == receipt.sha256:
            return PresenceRow(
                destination="getonboard",
                artifact="Tus CVs",
                state=PresenceState.IN_SYNC,
                evidence=evidence,
            )
        return PresenceRow(
            destination="getonboard",
            artifact="Tus CVs",
            state=PresenceState.STALE,
            evidence=evidence + " (local PDF hash differs)",
            hint="jobbot getonboard upload-cv --apply",
        )
    return PresenceRow(
        destination="getonboard",
        artifact="Tus CVs",
        state=PresenceState.STALE,
        evidence=evidence + " (local PDF missing)",
        hint="jobbot cv build",
    )


def _getonboard_profile(config: JobbotConfig, candidate: Candidate) -> PresenceRow:
    fields = load_permanent_profile(config.output_dir)
    md = permanent_profile_md_path(config.output_dir)
    plan = plan_getonboard(config, candidate)
    if fields is None and not md.is_file():
        return PresenceRow(
            destination="getonboard",
            artifact="permanent profile",
            state=PresenceState.MISSING,
            evidence="no draft under output/getonboard/",
            hint="jobbot getonboard prepare",
        )
    note = plan.note or "draft present"
    return PresenceRow(
        destination="getonboard",
        artifact="permanent profile",
        state=PresenceState.PRESENT,
        evidence=note,
        hint="jobbot getonboard sync --apply" if plan.actionable else None,
    )


def _indeed(config: JobbotConfig, candidate: Candidate) -> PresenceRow:
    plan = plan_indeed(config, candidate)
    if not plan.ready:
        return PresenceRow(
            destination="indeed",
            artifact="profile snapshot",
            state=PresenceState.BLOCKED,
            evidence=plan.blocked_reason or "unavailable",
            hint=plan.hint,
        )
    if plan.actionable:
        return PresenceRow(
            destination="indeed",
            artifact="profile snapshot",
            state=PresenceState.BEHIND,
            evidence=f"{len(plan.operations)} sync ops pending"
            + (f" · {plan.note}" if plan.note else ""),
            hint="jobbot indeed sync --apply",
        )
    return PresenceRow(
        destination="indeed",
        artifact="profile snapshot",
        state=PresenceState.OK,
        evidence=plan.note or "nothing to sync",
    )


def _linkedin(config: JobbotConfig, candidate: Candidate) -> PresenceRow:
    plan = plan_linkedin(config, candidate)
    if plan.note and not plan.operations:
        return PresenceRow(
            destination="linkedin",
            artifact="publications",
            state=PresenceState.OK,
            evidence=plan.note,
        )
    if plan.actionable:
        return PresenceRow(
            destination="linkedin",
            artifact="publications",
            state=PresenceState.PENDING,
            evidence=f"{len(plan.operations)} publication(s) to sync"
            + (f" · {plan.note}" if plan.note else ""),
            hint="jobbot linkedin sync --section publications --apply",
        )
    return PresenceRow(
        destination="linkedin",
        artifact="publications",
        state=PresenceState.OK,
        evidence=plan.note or "nothing pending",
    )
