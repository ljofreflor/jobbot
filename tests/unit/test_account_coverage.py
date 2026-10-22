"""Account coverage counts evidenced rows. It does not create an account."""

from __future__ import annotations

from jobbot.portals.profile_state import AccountState, PortalProfileState, account_coverage


def _row(portal: str, account: AccountState) -> PortalProfileState:
    return PortalProfileState(portal=portal, adapter="sheet", account=account)


def test_unknown_stays_in_the_denominator() -> None:
    states = [
        _row("alta", AccountState.evidenced),
        _row("bound", AccountState.identity_bound),
        _row("human", AccountState.needs_human),
        _row("open", AccountState.unknown),
    ]

    assert account_coverage(states) == (2, 4)


def test_excluded_and_out_of_scope_leave_both_sides() -> None:
    states = [
        _row("alta", AccountState.evidenced),
        _row("linkedin", AccountState.evidenced),
        _row("sii", AccountState.unknown),
    ]

    assert account_coverage(
        states,
        excluded=frozenset({"linkedin"}),
        out_of_scope=frozenset({"sii"}),
    ) == (1, 1)


def test_an_empty_tracker_is_zero() -> None:
    assert account_coverage([]) == (0, 0)
