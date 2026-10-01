"""Novel / unanswered form fields become a HITL GitHub issue — never invented (#44)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from jobbot.portals.field_diff import NewFieldCandidate
from jobbot.portals.field_gap_issue import (
    CURSOR_ASSIGNEE,
    create_field_gap_issue,
    draft_field_gap_issue,
    gaps_from_form,
)
from jobbot.portals.form_learn import FieldKind, learn_form_html

_FORM = """
<html><body>
<form>
  <label for="full_name">Full name</label>
  <input id="full_name" name="full_name" type="text">
  <label for="email">Email</label>
  <input id="email" name="email" type="email">
  <label for="years_xp">Years of AI experience</label>
  <input id="years_xp" name="years_xp" type="text">
  <label for="password">Password</label>
  <input id="password" name="password" type="password">
</form>
</body></html>
"""


def test_gaps_exclude_password_and_answered_labels() -> None:
    form = learn_form_html(_FORM, url="https://acme.wd3.myworkdayjobs.com/careers")
    gaps = gaps_from_form(form, answered_labels=["Full name", "Email"])
    assert "Years of AI experience" in gaps
    assert all("password" not in g.casefold() for g in gaps)


def test_draft_issue_includes_portal_and_gap_labels() -> None:
    draft = draft_field_gap_issue(
        company="Acme",
        portal_url="https://acme.wd3.myworkdayjobs.com/careers",
        ats="workday",
        gap_labels=["Years of AI experience"],
        job_id="J0114",
    )
    assert draft is not None
    assert "Acme" in draft.title
    assert "Years of AI experience" in draft.body
    assert "J0114" in draft.body
    assert "workday" in draft.body
    assert draft.assignee == CURSOR_ASSIGNEE
    assert "invent" in draft.body.casefold()


def test_create_issue_is_mocked_and_uses_assignee() -> None:
    draft = draft_field_gap_issue(
        company="Acme",
        portal_url="https://acme.example/careers",
        ats="unknown",
        gap_labels=["Visa status"],
        new_fields=[
            NewFieldCandidate(
                field_hash="abc",
                labels_seen=["Visa status"],
                kind=FieldKind.TEXT,
                portals=["acme.example"],
                required_count=1,
                total_count=1,
                options=[],
                example_accepts=[],
            )
        ],
    )
    assert draft is not None
    seen: list[list[str]] = []

    def runner(cmd: list[str]) -> subprocess.CompletedProcess[str]:
        seen.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="https://github.com/o/r/issues/99\n")

    url = create_field_gap_issue(draft, runner=runner)
    assert url.endswith("/issues/99")
    assert seen and seen[0][0] == "gh"
    assert "--assignee" in seen[0]
    assert CURSOR_ASSIGNEE in seen[0]


def test_no_gaps_means_no_draft() -> None:
    assert (
        draft_field_gap_issue(
            company="Acme",
            portal_url="https://boards.greenhouse.io/acme",
            ats="greenhouse",
            gap_labels=[],
        )
        is None
    )


class _Page:
    def __init__(self, html: str) -> None:
        self.html = html
        self.visited: list[str] = []
        self.filled: dict[str, str] = {}
        self.uploaded: list[tuple[str, str]] = []

    def goto(self, url: str, **_: object) -> None:
        self.visited.append(url)

    def content(self) -> str:
        return self.html

    def fill(self, selector: str, value: str) -> None:
        self.filled[selector] = value

    def locator(self, selector: str) -> object:
        class _Loc:
            def set_input_files(self, files: str) -> None:
                pass

            @property
            def first(self) -> _Loc:
                return self

        return _Loc()


def test_signup_fill_persists_gaps_without_inventing(tmp_path: Path) -> None:
    """End-to-end of the apply result: form gaps → issue draft, submitted False."""
    from jobbot.companies.models import KnowledgeStatus
    from jobbot.companies.signup import AccountNeed
    from jobbot.cv.company_apply import company_apply_intent, perform_company_apply
    from jobbot.cv.sync import CompanySyncRow
    from jobbot.models.candidate import Candidate
    from jobbot.portals.detect import AtsKind
    from tests.fixtures.profile import sample_profile_dict

    candidate = Candidate.model_validate(sample_profile_dict())
    row = CompanySyncRow(
        company_id="acme",
        company_name="Acme",
        url="https://acme.wd3.myworkdayjobs.com/careers",
        ats=AtsKind.WORKDAY,
        need=AccountNeed.NEEDED,
        action="needs_account",
        hint="signup",
        status=KnowledgeStatus.ACTIVE,
        session_evidenced=False,
    )
    intent = company_apply_intent(row, candidate, cv_path=None)
    assert intent.mode == "signup_fill"
    page = _Page(_FORM)
    result = perform_company_apply(
        intent,
        candidate,
        page=page,
        output_dir=tmp_path / "output",
        ats="workday",
    )
    assert result.submitted is False
    assert "password" not in " ".join(result.filled).casefold()
    assert result.gap_issue is not None
    assert "Years of AI experience" in result.gap_labels or (
        "Years of AI experience" in result.gap_issue.body
    )
