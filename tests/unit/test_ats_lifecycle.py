"""ATS lifecycle: knowledge + account/session + field gaps (#44)."""

from __future__ import annotations

from jobbot.companies.models import KnowledgeStatus
from jobbot.companies.signup import AccountNeed
from jobbot.portals.ats_lifecycle import (
    AccountSessionState,
    FieldGapState,
    PortalAction,
    account_session_state,
    field_gap_state,
    next_portal_action,
)


def test_workday_without_receipt_needs_signup() -> None:
    state = account_session_state(
        need=AccountNeed.NEEDED,
        has_account_evidence=False,
    )
    assert state is AccountSessionState.NEEDS_SIGNUP
    assert (
        next_portal_action(
            knowledge=KnowledgeStatus.ACTIVE,
            session=state,
            sync_action="needs_account",
        )
        is PortalAction.SIGNUP_FILL
    )


def test_workday_with_receipt_needs_login_only() -> None:
    state = account_session_state(
        need=AccountNeed.NEEDED,
        has_account_evidence=True,
    )
    assert state is AccountSessionState.NEEDS_LOGIN
    assert (
        next_portal_action(
            knowledge=KnowledgeStatus.ACTIVE,
            session=state,
            sync_action="needs_account",
        )
        is PortalAction.LOGIN
    )


def test_greenhouse_does_not_need_an_account() -> None:
    state = account_session_state(
        need=AccountNeed.NOT_NEEDED,
        has_account_evidence=False,
    )
    assert state is AccountSessionState.NOT_NEEDED
    assert (
        next_portal_action(
            knowledge=KnowledgeStatus.ACTIVE,
            session=state,
            sync_action="update_profile",
        )
        is PortalAction.FILL
    )


def test_profile_receipt_is_stronger_than_account_flag() -> None:
    state = account_session_state(
        need=AccountNeed.NEEDED,
        has_account_evidence=True,
        has_profile_receipt=True,
    )
    assert state is AccountSessionState.PROFILE_PRESENT


def test_rejected_knowledge_skips() -> None:
    assert (
        next_portal_action(
            knowledge=KnowledgeStatus.REJECTED,
            session=AccountSessionState.NEEDS_SIGNUP,
        )
        is PortalAction.SKIP
    )


def test_field_gap_lifecycle() -> None:
    assert field_gap_state(unanswered=False) is FieldGapState.OBSERVED
    assert field_gap_state(unanswered=True) is FieldGapState.GAP
    assert (
        field_gap_state(unanswered=True, issue_url="https://github.com/x/y/issues/1")
        is FieldGapState.ISSUE_OPEN
    )
