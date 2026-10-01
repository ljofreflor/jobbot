"""ATS portal lifecycle: knowledge, account/session, and form-field gaps.

Three axes, one vocabulary. Knowledge status lives in ``companies.models``;
this module decides the *next action* for account/session and field gaps from
local evidence only — never from a tab on the host alone.
"""

from __future__ import annotations

from enum import StrEnum

from jobbot.companies.models import KnowledgeStatus
from jobbot.companies.signup import AccountNeed


class AccountSessionState(StrEnum):
    """Whether this workspace still needs to register, only sign in, or is done."""

    NOT_NEEDED = "not_needed"
    NEEDS_SIGNUP = "needs_signup"
    NEEDS_LOGIN = "needs_login"
    AWAITING_HUMAN = "awaiting_human"
    SESSION_READY = "session_ready"
    PROFILE_PRESENT = "profile_present"


class FieldGapState(StrEnum):
    """How an unanswered / novel form field progresses (never invented)."""

    OBSERVED = "observed"
    GAP = "gap"
    ISSUE_OPEN = "issue_open"
    PROFILE_EXTENDED = "profile_extended"
    PORTAL_ONLY = "portal_only"


class PortalAction(StrEnum):
    """What JobBot may do next for one career site."""

    SKIP = "skip"
    LOGIN = "login"
    SIGNUP_FILL = "signup_fill"
    FILL = "fill"


def account_session_state(
    *,
    need: AccountNeed,
    has_account_evidence: bool,
    has_profile_receipt: bool = False,
) -> AccountSessionState:
    """Map account need + local evidence → session state.

    ``has_account_evidence`` means a prior page receipt / known account — not a
    Chrome tab on the host. ``has_profile_receipt`` is stronger: the page showed
    a profile fact for this candidate.
    """
    if need is AccountNeed.NOT_NEEDED:
        return AccountSessionState.NOT_NEEDED
    if has_profile_receipt:
        return AccountSessionState.PROFILE_PRESENT
    if has_account_evidence:
        return AccountSessionState.NEEDS_LOGIN
    if need is AccountNeed.NEEDED:
        return AccountSessionState.NEEDS_SIGNUP
    # UNKNOWN: treat like signup until evidence says otherwise (do not assume away).
    return AccountSessionState.NEEDS_SIGNUP


def next_portal_action(
    *,
    knowledge: KnowledgeStatus,
    session: AccountSessionState,
    sync_action: str | None = None,
) -> PortalAction:
    """Next automatable step. Irreversible clicks stay human either way."""
    if knowledge is KnowledgeStatus.REJECTED:
        return PortalAction.SKIP
    if session is AccountSessionState.NOT_NEEDED:
        if sync_action == "update_profile" and knowledge is KnowledgeStatus.ACTIVE:
            return PortalAction.FILL
        return PortalAction.SKIP
    if session is AccountSessionState.PROFILE_PRESENT:
        if sync_action == "update_profile":
            return PortalAction.FILL
        return PortalAction.SKIP
    if session is AccountSessionState.NEEDS_LOGIN:
        return PortalAction.LOGIN
    if session is AccountSessionState.NEEDS_SIGNUP:
        return PortalAction.SIGNUP_FILL
    return PortalAction.SKIP


def field_gap_state(*, unanswered: bool, issue_url: str | None = None) -> FieldGapState:
    """A field without a profile answer starts as gap; an issue moves it forward."""
    if issue_url:
        return FieldGapState.ISSUE_OPEN
    if unanswered:
        return FieldGapState.GAP
    return FieldGapState.OBSERVED
