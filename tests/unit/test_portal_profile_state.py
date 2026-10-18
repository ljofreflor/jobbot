"""Coverage math for portal profiles. No network, no browser."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from jobbot.models.candidate import Candidate
from jobbot.portals.profile_state import (
    AccountState,
    Drift,
    EvidenceKind,
    PortalProfileState,
    Priority,
    UpdateRecord,
    coverage_report,
    load_states,
    mark_updated,
    projection_hash,
    section_hash,
)
from tests.fixtures.profile import non_data_profile_dict

NOW = datetime(2026, 10, 18, tzinfo=UTC)
CV = "sha256:cv"
SECTIONS = [
    "identity",
    "headline",
    "summary",
    "experience",
    "education",
    "skills",
    "languages",
    "cv",
]


def _candidate() -> Candidate:
    return Candidate.model_validate(non_data_profile_dict())


def _synced(
    candidate: Candidate,
    portal: str,
    *,
    priority: Priority,
    account: AccountState = AccountState.evidenced,
    author: str = "jobbot",
) -> PortalProfileState:
    hashes: dict[str, str] = {}
    authors: dict[str, str] = {}
    for section in SECTIONS:
        digest = section_hash(candidate, section, cv_sha256=CV)
        if digest is None:
            continue
        hashes[section] = digest
        authors[section] = author
    return PortalProfileState(
        portal=portal,
        adapter="generic",
        priority=priority,
        account=account,
        sections=list(SECTIONS),
        section_hashes=hashes,
        section_authors=authors,
        cv_variant="base_es",
        cv_sha256=CV,
        sst_hash=projection_hash(candidate, SECTIONS, cv_sha256=CV),
        last_push=NOW,
        updates=[
            UpdateRecord(
                at=NOW,
                by=author,
                sections=list(hashes),
                evidence=EvidenceKind.receipt,
            )
        ],
    )


def test_weighted_kpi_matches_the_three_portal_fixture() -> None:
    """High fully in sync, medium with experience drifted, low unknown → 11/14."""
    candidate = _candidate()
    high = _synced(candidate, "alta", priority=Priority.high)
    medium = _synced(candidate, "media", priority=Priority.medium, author="manual")
    medium.section_hashes["experience"] = "sha256:stale"
    low = PortalProfileState(
        portal="baja",
        adapter="generic",
        priority=Priority.low,
        account=AccountState.unknown,
        sections=["identity"],
    )

    report = coverage_report(
        [high, medium, low],
        candidate,
        now=NOW,
        cv_hashes={"base_es": CV},
    )
    by_id = {row.portal: row for row in report.portals}

    assert by_id["alta"].status is Drift.in_sync
    assert by_id["alta"].level == 3
    assert (by_id["alta"].covered, by_id["alta"].applicable) == (7, 7)
    assert by_id["media"].status is Drift.sst_changed
    assert by_id["media"].level == 2
    assert (by_id["media"].covered, by_id["media"].applicable) == (6, 7)
    assert by_id["baja"].status is Drift.unknown
    assert by_id["baja"].level == 0
    assert by_id["baja"].coverage == 0
    assert (report.kpi_num, report.kpi_den) == (11, 14)
    assert report.sst_gap == 2


def test_search_queries_do_not_move_the_projection() -> None:
    candidate = _candidate()
    before = projection_hash(candidate, SECTIONS, cv_sha256=CV)
    candidate.search_queries.append("a preference, not a fact")

    assert projection_hash(candidate, SECTIONS, cv_sha256=CV) == before

    state = _synced(candidate, "alta", priority=Priority.high)
    report = coverage_report([state], candidate, now=NOW, cv_hashes={"base_es": CV})
    assert report.portals[0].status is Drift.in_sync


def test_a_fact_the_portal_does_not_project_does_not_move_its_hash() -> None:
    candidate = _candidate()
    before = projection_hash(candidate, ["identity"], cv_sha256=CV)
    candidate.experience[0].title = "Otro cargo"

    assert projection_hash(candidate, ["identity"], cv_sha256=CV) == before


def test_mark_updated_without_evidence_stays_unknown() -> None:
    candidate = _candidate()
    state = PortalProfileState(
        portal="alta",
        adapter="generic",
        priority=Priority.high,
        account=AccountState.evidenced,
        sections=["identity"],
    )
    declared = mark_updated(
        state,
        sections=["identity"],
        evidence=EvidenceKind.none,
        by="manual",
        now=NOW,
        candidate=candidate,
        current_cv_sha256=CV,
    )
    report = coverage_report([declared], candidate, now=NOW, cv_hashes={"base_es": CV})

    assert declared.section_hashes == {}
    assert report.portals[0].status is Drift.unknown
    assert report.kpi == 0


def test_mark_updated_with_a_receipt_covers_the_section() -> None:
    candidate = _candidate()
    state = PortalProfileState(
        portal="alta",
        adapter="generic",
        priority=Priority.high,
        account=AccountState.evidenced,
        sections=["identity", "languages"],
    )
    recorded = mark_updated(
        state,
        sections=["identity", "languages"],
        evidence=EvidenceKind.receipt,
        by="manual",
        now=NOW,
        candidate=candidate,
        current_cv_sha256=None,
    )
    report = coverage_report([recorded], candidate, now=NOW)

    identity = next(item for item in report.portals[0].sections if item.section == "identity")
    languages = next(item for item in report.portals[0].sections if item.section == "languages")
    assert identity.covered is True
    assert languages.sst_gap is True
    assert languages.covered is False
    assert report.portals[0].coverage == 1


def test_expired_maintenance_is_due_and_not_covered() -> None:
    candidate = _candidate()
    state = _synced(candidate, "alta", priority=Priority.high)
    state.last_push = NOW - timedelta(days=90)
    state.updates[0].at = NOW - timedelta(days=90)
    state.maintenance_days = 30

    report = coverage_report([state], candidate, now=NOW, cv_hashes={"base_es": CV})

    assert report.portals[0].status is Drift.due
    assert report.portals[0].covered == 0
    assert report.due == 1


def test_load_rejects_an_unknown_key(tmp_path: Path) -> None:
    from jobbot.portals.profile_state import ProfileStateError

    target = tmp_path / "portal_profiles.yaml"
    target.write_text(
        "- portal: alta\n  adapter: generic\n  invented: yes\n",
        encoding="utf-8",
    )
    try:
        load_states(target)
    except ProfileStateError as exc:
        assert "invented" in str(exc)
    else:
        raise AssertionError("unknown key was accepted")
