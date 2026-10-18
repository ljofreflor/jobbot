"""Per-portal profile state, drift and coverage. No browser, no network.

The state file is local (`data/portal_profiles.yaml`). Hashes cover only the
facts a portal projects from the source of truth. Search queries are a
preference, not a fact, and never move a hash.
"""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from fractions import Fraction
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from jobbot.models.candidate import Candidate

CANONICAL_SECTIONS: tuple[str, ...] = (
    "identity",
    "headline",
    "summary",
    "experience",
    "education",
    "languages",
    "certifications",
    "skills",
    "cv",
)

_PRIORITY_WEIGHT = {"high": 3, "medium": 2, "low": 1}

IMPORT_COLUMNS = frozenset(
    {
        "portal",
        "adapter",
        "priority",
        "account",
        "login_method",
        "email_alias",
        "account_owner",
        "signup_url",
        "profile_url",
        "cv_variant",
        "sections",
        "maintenance_days",
    }
)


class ProfileStateError(ValueError):
    """The state file or a command argument cannot be used."""


class AccountState(StrEnum):
    evidenced = "evidenced"
    needs_human = "needs_human"
    identity_bound = "identity_bound"
    unknown = "unknown"


class Priority(StrEnum):
    high = "high"
    medium = "medium"
    low = "low"


class EvidenceKind(StrEnum):
    diff = "diff"
    receipt = "receipt"
    none = "none"


class Drift(StrEnum):
    in_sync = "in_sync"
    sst_changed = "sst_changed"
    portal_changed = "portal_changed"
    both = "both"
    due = "due"
    needs_human = "needs_human"
    unknown = "unknown"


class UpdateRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    at: datetime
    by: str
    sections: list[str] = Field(default_factory=list)
    evidence: EvidenceKind = EvidenceKind.none
    note: str | None = None


class PortalProfileState(BaseModel):
    """One portal's local sync record. Unknown keys are rejected."""

    model_config = ConfigDict(extra="forbid")

    portal: str = Field(min_length=1)
    adapter: str = Field(min_length=1)
    priority: Priority = Priority.medium
    account: AccountState = AccountState.unknown
    login_method: str = "unknown"
    email_alias: str | None = None
    account_owner: str = "candidate"
    signup_url: str | None = None
    profile_url: str | None = None
    cv_variant: str = "base_es"
    cv_sha256: str | None = None
    sst_hash: str | None = None
    portal_hash: str | None = None
    sections: list[str] = Field(default_factory=list)
    section_hashes: dict[str, str] = Field(default_factory=dict)
    section_portal_hashes: dict[str, str] = Field(default_factory=dict)
    section_authors: dict[str, str] = Field(default_factory=dict)
    last_pull: datetime | None = None
    last_push: datetime | None = None
    updates: list[UpdateRecord] = Field(default_factory=list)
    maintenance_days: int = 60
    gaps: list[str] = Field(default_factory=list)


class SectionView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section: str
    status: Drift
    applicable: bool
    covered: bool
    sst_gap: bool
    by: str | None = None


class PortalView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    portal: str
    adapter: str
    priority: Priority
    account: AccountState
    status: Drift
    level: int
    coverage: float
    covered: int
    applicable: int
    sst_gap: int
    cv_current: bool
    last_update: str | None
    next_maintenance: str | None
    sections: list[SectionView]


class CoverageReport(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kpi_num: int
    kpi_den: int
    kpi: float
    automation: float
    sst_gap: int
    due: int
    portals: list[PortalView]

    def to_public_dict(self) -> dict[str, Any]:
        """Numbers and labels only. No profile values."""
        return self.model_dump(mode="json")


def default_state_path(root: Path) -> Path:
    return root / "data" / "portal_profiles.yaml"


def default_alias_path(root: Path) -> Path:
    return root / "data" / "aliases.yaml"


def cv_hashes_from_output(root: Path) -> dict[str, str]:
    """SHA-256 of a CV already built in this workspace. Missing files are omitted."""
    paths = {
        "base_es": root / "output" / "base" / "cv.pdf",
        "base_en": root / "output" / "en" / "base" / "cv.pdf",
        "ats_txt": root / "output" / "base" / "cv_ats.txt",
    }
    found: dict[str, str] = {}
    for variant, path in paths.items():
        if path.is_file():
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            found[variant] = "sha256:" + digest
    return found


def _sha(payload: object) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()


def section_payload(candidate: Candidate, section: str) -> dict[str, Any] | None:
    """Facts the source of truth holds for one canonical section.

    ``None`` means the portal asks and the source of truth does not answer.
    Search queries are never part of a payload.
    """
    if section not in CANONICAL_SECTIONS:
        msg = f"unknown section: {section}"
        raise ProfileStateError(msg)
    personal = candidate.personal
    if section == "identity":
        return {
            "name": personal.name,
            "city": personal.city,
            "country": personal.country,
            "phone": personal.phone,
            "linkedin": personal.linkedin,
            "github": personal.github,
            "orcid": personal.orcid,
        }
    if section == "headline":
        return {"headline": personal.headline} if personal.headline else None
    if section == "summary":
        text = (candidate.summary or "").strip()
        return {"summary": text} if text else None
    if section == "experience":
        if not candidate.experience:
            return None
        rows = [
            {
                "id": item.id,
                "company": item.company,
                "title": item.title,
                "location": item.location,
                "start_date": item.start_date,
                "end_date": item.end_date,
                "current": item.current,
                "description": item.description,
                "achievements": [a.text for a in item.achievements],
            }
            for item in candidate.experience
        ]
        return {"experience": rows}
    if section == "education":
        if not candidate.education:
            return None
        rows = [
            {
                "id": item.id,
                "institution": item.institution,
                "degree": item.degree,
                "start_date": item.start_date,
                "end_date": item.end_date,
                "details": item.details,
            }
            for item in candidate.education
        ]
        return {"education": rows}
    if section == "languages":
        return None
    if section == "certifications":
        return None
    if section == "skills":
        names = candidate.skills.all_skills()
        if not names and not candidate.specialties:
            return None
        return {"skills": names, "specialties": list(candidate.specialties)}
    if section == "cv":
        return {"cv": "built-from-sst"}
    msg = f"unknown section: {section}"
    raise ProfileStateError(msg)


def section_hash(
    candidate: Candidate,
    section: str,
    *,
    cv_sha256: str | None = None,
) -> str | None:
    if section == "cv":
        return cv_sha256
    payload = section_payload(candidate, section)
    if payload is None:
        return None
    return _sha(payload)


def projection_hash(
    candidate: Candidate,
    sections: list[str],
    *,
    cv_sha256: str | None = None,
) -> str:
    """Hash of the facts this portal projects. Other facts do not move it."""
    projected: dict[str, str] = {}
    for section in sections:
        digest = section_hash(candidate, section, cv_sha256=cv_sha256)
        if digest is not None:
            projected[section] = digest
    return _sha(projected)


def _unknown_key(exc: ValidationError) -> str | None:
    for err in exc.errors():
        if err.get("type") == "extra_forbidden" and err.get("loc"):
            return str(err["loc"][0])
    return None


def load_states(path: Path) -> list[PortalProfileState]:
    if not path.is_file():
        return []
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        return []
    if not isinstance(raw, list):
        msg = f"{path.name} must be a list of portals"
        raise ProfileStateError(msg)
    states: list[PortalProfileState] = []
    for item in raw:
        if not isinstance(item, dict):
            msg = "each portal must be a mapping"
            raise ProfileStateError(msg)
        try:
            states.append(PortalProfileState.model_validate(item))
        except ValidationError as exc:
            key = _unknown_key(exc)
            if key is not None:
                msg = f"unknown key: {key}"
                raise ProfileStateError(msg) from exc
            raise ProfileStateError(str(exc)) from exc
    return states


def save_states(states: list[PortalProfileState], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = [item.model_dump(mode="json") for item in states]
    path.write_text(
        yaml.safe_dump(payload, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


def load_aliases(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        msg = "aliases file must be a mapping"
        raise ProfileStateError(msg)
    block = raw.get("aliases", raw)
    if not isinstance(block, dict):
        msg = "aliases must be a mapping of label → address"
        raise ProfileStateError(msg)
    return {str(key): str(value) for key, value in block.items()}


def _last_evidence(state: PortalProfileState) -> EvidenceKind | None:
    if not state.updates:
        return None
    return state.updates[-1].evidence


def _reference_time(state: PortalProfileState) -> datetime | None:
    stamped = [item for item in (state.last_push, state.last_pull) if item is not None]
    if state.updates:
        stamped.append(state.updates[-1].at)
    if not stamped:
        return None
    latest = max(stamped)
    if latest.tzinfo is None:
        return latest.replace(tzinfo=UTC)
    return latest.astimezone(UTC)


def _is_due(state: PortalProfileState, now: datetime) -> bool:
    if state.maintenance_days <= 0:
        return False
    reference = _reference_time(state)
    if reference is None:
        return False
    current = now if now.tzinfo else now.replace(tzinfo=UTC)
    return current - reference >= timedelta(days=state.maintenance_days)


def evaluate_portal(
    state: PortalProfileState,
    candidate: Candidate | None,
    *,
    now: datetime,
    current_cv_sha256: str | None,
) -> PortalView:
    """Coverage of one portal. A declaration without evidence stays unknown."""
    gap_names = list(state.gaps)
    views: list[SectionView] = []
    forced_unknown = (
        _last_evidence(state) is EvidenceKind.none
        or candidate is None
        or state.account is AccountState.unknown
    )
    due = _is_due(state, now) and not forced_unknown

    for section in state.sections:
        if section not in CANONICAL_SECTIONS:
            msg = f"unknown section: {section}"
            raise ProfileStateError(msg)
        digest = (
            section_hash(candidate, section, cv_sha256=current_cv_sha256)
            if candidate is not None
            else None
        )
        sst_gap = section != "cv" and digest is None
        applicable = not sst_gap
        if sst_gap:
            gap_names.append(section)
        stored = state.section_hashes.get(section)
        portal_stored = state.section_portal_hashes.get(section)
        status = Drift.unknown
        covered = False
        if forced_unknown:
            status = Drift.unknown
        elif sst_gap:
            status = Drift.needs_human
        elif digest is None or stored is None:
            status = Drift.unknown
        else:
            sst_changed = stored != digest
            portal_changed = portal_stored is not None and portal_stored != stored
            if sst_changed and portal_changed:
                status = Drift.both
            elif sst_changed:
                status = Drift.sst_changed
            elif portal_changed:
                status = Drift.portal_changed
            elif due:
                status = Drift.due
            else:
                status = Drift.in_sync
                covered = True
        views.append(
            SectionView(
                section=section,
                status=status,
                applicable=applicable,
                covered=covered,
                sst_gap=sst_gap,
                by=state.section_authors.get(section),
            )
        )

    applicable_n = sum(1 for item in views if item.applicable)
    covered_n = sum(1 for item in views if item.covered)
    coverage = (covered_n / applicable_n) if applicable_n else 0.0
    portal_status = _portal_status(state, views, forced_unknown=forced_unknown, due=due)
    cv_current = bool(
        state.cv_sha256 and current_cv_sha256 and state.cv_sha256 == current_cv_sha256
    )
    level = _level(state, coverage, cv_current, portal_status)
    reference = _reference_time(state)
    next_at = None
    if reference is not None and state.maintenance_days > 0:
        next_at = (reference + timedelta(days=state.maintenance_days)).date().isoformat()
    last = state.updates[-1].at.date().isoformat() if state.updates else None
    return PortalView(
        portal=state.portal,
        adapter=state.adapter,
        priority=state.priority,
        account=state.account,
        status=portal_status,
        level=level,
        coverage=coverage,
        covered=covered_n,
        applicable=applicable_n,
        sst_gap=len(dict.fromkeys(gap_names)),
        cv_current=cv_current,
        last_update=last,
        next_maintenance=next_at,
        sections=views,
    )


def _portal_status(
    state: PortalProfileState,
    views: list[SectionView],
    *,
    forced_unknown: bool,
    due: bool,
) -> Drift:
    if forced_unknown or state.account is AccountState.unknown:
        return Drift.unknown
    if not views:
        return Drift.unknown
    statuses = {item.status for item in views if item.applicable}
    if Drift.both in statuses or (
        Drift.sst_changed in statuses and Drift.portal_changed in statuses
    ):
        return Drift.both
    if Drift.sst_changed in statuses:
        return Drift.sst_changed
    if Drift.portal_changed in statuses:
        return Drift.portal_changed
    if due or Drift.due in statuses:
        return Drift.due
    if statuses <= {Drift.in_sync} and statuses:
        return Drift.in_sync
    if statuses <= {Drift.needs_human}:
        return Drift.needs_human
    return Drift.unknown


def _level(
    state: PortalProfileState,
    coverage: float,
    cv_current: bool,
    status: Drift,
) -> int:
    if state.account is not AccountState.evidenced or status is Drift.unknown:
        return 0
    if coverage == 1.0 and status is Drift.in_sync:
        return 3
    if cv_current:
        return 2
    return 1


def coverage_report(
    states: list[PortalProfileState],
    candidate: Candidate | None,
    *,
    now: datetime,
    cv_hashes: dict[str, str] | None = None,
) -> CoverageReport:
    hashes = cv_hashes or {}
    portals = [
        evaluate_portal(
            state,
            candidate,
            now=now,
            current_cv_sha256=hashes.get(state.cv_variant),
        )
        for state in states
    ]
    # KPI = Σ (weight × c_p) / Σ weight. A portal with nothing applicable has
    # c_p = 0 and still adds its weight, so leaving it out cannot raise the KPI.
    total = Fraction(0)
    weight_sum = 0
    jobbot_covered = 0
    covered_total = 0
    gap = 0
    due = 0
    for state, view in zip(states, portals, strict=True):
        weight = _PRIORITY_WEIGHT[state.priority.value]
        weight_sum += weight
        if view.applicable:
            total += Fraction(weight * view.covered, view.applicable)
        jobbot_covered += sum(1 for item in view.sections if item.covered and item.by == "jobbot")
        covered_total += view.covered
        gap += view.sst_gap
        if view.status is Drift.due:
            due += 1
    kpi_fraction = (total / weight_sum) if weight_sum else Fraction(0)
    num = kpi_fraction.numerator
    den = kpi_fraction.denominator
    kpi = float(kpi_fraction)
    automation = (jobbot_covered / covered_total) if covered_total else 0.0
    return CoverageReport(
        kpi_num=num,
        kpi_den=den,
        kpi=kpi,
        automation=automation,
        sst_gap=gap,
        due=due,
        portals=portals,
    )


def mark_updated(
    state: PortalProfileState,
    *,
    sections: list[str],
    evidence: EvidenceKind,
    by: str,
    now: datetime,
    candidate: Candidate | None,
    current_cv_sha256: str | None,
    note: str | None = None,
) -> PortalProfileState:
    """Record a manual update. ``none`` does not store hashes and cannot raise coverage."""
    unknown = [item for item in sections if item not in CANONICAL_SECTIONS]
    if unknown:
        msg = f"unknown section: {unknown[0]}"
        raise ProfileStateError(msg)
    updated = state.model_copy(deep=True)
    updated.updates.append(
        UpdateRecord(at=now, by=by, sections=list(sections), evidence=evidence, note=note)
    )
    if evidence is EvidenceKind.none:
        return updated
    if candidate is None:
        msg = "a receipt needs the source of truth so the section hash can be stored"
        raise ProfileStateError(msg)
    for section in sections:
        digest = section_hash(candidate, section, cv_sha256=current_cv_sha256)
        if digest is None:
            continue
        updated.section_hashes[section] = digest
        updated.section_authors[section] = by
        if section == "cv":
            updated.cv_sha256 = current_cv_sha256
    updated.sst_hash = projection_hash(candidate, updated.sections, cv_sha256=current_cv_sha256)
    updated.last_push = now
    return updated


class ImportPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    portals: list[str]
    ignored_columns: list[str]
    rows: list[PortalProfileState]


def preview_import(csv_path: Path) -> ImportPreview:
    with csv_path.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        ignored = [name for name in fieldnames if name not in IMPORT_COLUMNS]
        rows: list[PortalProfileState] = []
        for raw in reader:
            sections = [
                item.strip() for item in (raw.get("sections") or "").split(",") if item.strip()
            ]
            days = raw.get("maintenance_days") or "60"
            rows.append(
                PortalProfileState(
                    portal=(raw.get("portal") or "").strip(),
                    adapter=(raw.get("adapter") or "generic").strip(),
                    priority=Priority((raw.get("priority") or "medium").strip()),
                    account=AccountState((raw.get("account") or "unknown").strip()),
                    login_method=(raw.get("login_method") or "unknown").strip(),
                    email_alias=(raw.get("email_alias") or "").strip() or None,
                    account_owner=(raw.get("account_owner") or "candidate").strip(),
                    signup_url=(raw.get("signup_url") or "").strip() or None,
                    profile_url=(raw.get("profile_url") or "").strip() or None,
                    cv_variant=(raw.get("cv_variant") or "base_es").strip(),
                    sections=sections,
                    maintenance_days=int(days),
                )
            )
    if any(not row.portal for row in rows):
        msg = "import row is missing portal"
        raise ProfileStateError(msg)
    return ImportPreview(
        portals=[row.portal for row in rows],
        ignored_columns=ignored,
        rows=rows,
    )
