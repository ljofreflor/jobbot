"""OMS/WHO Taleo account signup adapter (#438). Offline fixtures only."""

from __future__ import annotations

from pathlib import Path

from jobbot.adapters.ats.signup_fill import build_fill_plan
from jobbot.adapters.taleo.signup import (
    OMS_WHO,
    SignupRecognize,
    account_evidence,
    portal_for_id,
    recognize_signup_html,
    registration_url,
    render_taleo_sheet,
    signup_items,
)
from jobbot.companies.models import CareerSite, CareerSiteType, KnowledgeStatus
from jobbot.companies.signup import AccountNeed, signup_target
from jobbot.models.candidate import Candidate
from jobbot.portals.detect import AtsKind
from jobbot.portals.fill_catalog import fill_portal
from jobbot.portals.profile_state import AccountState
from tests.fixtures.profile import sample_profile_dict

FIXTURES = Path("tests/fixtures/taleo")
SIGNUP_URL = "https://careers.example.org/careersection/ex/accesscontrol.ftl?lang=en"


def _candidate() -> Candidate:
    return Candidate.model_validate(sample_profile_dict())


def _site(url: str) -> CareerSite:
    return CareerSite(
        url=url,
        domain=url.split("//", 1)[-1].split("/", 1)[0],
        site_type=CareerSiteType.COMPANY_CAREER_PORTAL,
        ats=AtsKind.TALEO,
        status=KnowledgeStatus.ACTIVE,
    )


def test_oms_who_is_registered_as_taleo_portal() -> None:
    assert portal_for_id("oms_who") is OMS_WHO
    catalog = fill_portal("oms_who")
    assert catalog is not None
    assert catalog.adapter == "taleo"
    assert "accesscontrol.ftl" in catalog.signup_url


def test_taleo_ats_needs_an_account_and_points_at_accesscontrol() -> None:
    jobsearch = "https://careers.example.org/careersection/ex/jobsearch.ftl?lang=en"
    target = signup_target(_site(jobsearch))

    assert target.need is AccountNeed.NEEDED
    assert target.url == (
        "https://careers.example.org/careersection/ex/accesscontrol.ftl?lang=en"
    )


def test_registration_url_leaves_accesscontrol_alone() -> None:
    assert registration_url(SIGNUP_URL) == SIGNUP_URL


def test_registration_url_from_jobdetail() -> None:
    detail = "https://careers.example.org/careersection/ex/jobdetail.ftl?job=123&lang=en"
    assert registration_url(detail) == (
        "https://careers.example.org/careersection/ex/accesscontrol.ftl?lang=en"
    )


def test_sheet_fills_known_fields_and_never_a_password() -> None:
    items = {item.label: item for item in signup_items(_candidate())}

    assert items["First Name"].value
    assert items["Email Address"].value
    assert items["Password"].value == ""
    assert items["Password"].yours_to_decide
    assert items["Create Account"].value == ""
    text = " ".join(f"{i.label}:{i.value}" for i in items.values()).casefold()
    assert "password:" in text
    # No invented credential next to Password
    assert items["Confirm Password"].value == ""


def test_render_sheet_uses_alias_never_raw_sst_email_when_alias_set() -> None:
    sheet = render_taleo_sheet(
        OMS_WHO,
        _candidate(),
        {"who-alias": "candidate+jobbot@example.org"},
        email_alias="who-alias",
    )
    assert "oms_who" in sheet
    assert "who-alias → candidate+jobbot@example.org" in sheet
    assert "Password: needs_human" in sheet
    assert "Create Account: needs_human" in sheet
    # Real SST email must not appear when an alias is configured.
    assert str(_candidate().personal.email) not in sheet


def test_recognize_signup_form_from_fixture() -> None:
    html = (FIXTURES / "oms_who_signup.html").read_text(encoding="utf-8")
    status, form = recognize_signup_html(html, url=SIGNUP_URL)

    assert status is SignupRecognize.OK
    assert form is not None
    assert form.readable
    labels = {field.label.casefold() for field in form.fields}
    assert "email address" in labels or "email" in labels


def test_captcha_page_is_manual_challenge() -> None:
    html = (FIXTURES / "oms_who_captcha.html").read_text(encoding="utf-8")
    status, form = recognize_signup_html(html, url=SIGNUP_URL)

    assert status is SignupRecognize.MANUAL_CHALLENGE
    assert form is None
    assert account_evidence(html) is AccountState.needs_human


def test_unrelated_page_is_ui_changed() -> None:
    html = (FIXTURES / "oms_who_ui_changed.html").read_text(encoding="utf-8")
    status, form = recognize_signup_html(html, url=SIGNUP_URL)

    assert status is SignupRecognize.UI_CHANGED
    assert form is None or not form.readable or status is SignupRecognize.UI_CHANGED


def test_candidate_home_fixture_is_evidenced() -> None:
    html = (FIXTURES / "oms_who_candidate_home.html").read_text(encoding="utf-8")
    assert account_evidence(html) is AccountState.evidenced


def test_fill_plan_never_submits_and_skips_password() -> None:
    html = (FIXTURES / "oms_who_signup.html").read_text(encoding="utf-8")
    _, form = recognize_signup_html(html, url=SIGNUP_URL)
    assert form is not None

    plan = build_fill_plan(
        _candidate(),
        SIGNUP_URL,
        AccountNeed.NEEDED,
        form=form,
    )

    assert plan.will_submit is False
    joined = " ".join(plan.fields_to_fill).casefold()
    assert "password" not in joined
    manual = " ".join(plan.needs_manual).casefold()
    assert "password" in manual
    assert "create" in manual or "submit" in manual
