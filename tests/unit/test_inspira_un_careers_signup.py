"""UN Careers / Inspira account signup adapter (#437). Offline fixtures only."""

from __future__ import annotations

from pathlib import Path

from jobbot.adapters.ats.signup_fill import build_fill_plan
from jobbot.adapters.inspira.signup import (
    UN_CAREERS,
    SignupRecognize,
    account_evidence,
    portal_for_id,
    recognize_signup_html,
    registration_url,
    render_inspira_sheet,
    signup_items,
)
from jobbot.companies.models import CareerSite, CareerSiteType, KnowledgeStatus
from jobbot.companies.signup import AccountNeed, signup_target
from jobbot.models.candidate import Candidate
from jobbot.portals.detect import AtsKind, detect_ats
from jobbot.portals.fill_catalog import fill_portal
from jobbot.portals.profile_state import AccountState
from tests.fixtures.profile import sample_profile_dict

FIXTURES = Path("tests/fixtures/inspira")
SIGNUP_URL = (
    "https://inspira.example.org/psc/REGISTER/EMPLOYEE/HRMS/c/"
    "UN_SKILL_REG.UN_SKILL_REG.GBL?languagecd=ENG"
)


def _candidate() -> Candidate:
    return Candidate.model_validate(sample_profile_dict())


def _site(url: str) -> CareerSite:
    return CareerSite(
        url=url,
        domain=url.split("//", 1)[-1].split("/", 1)[0],
        site_type=CareerSiteType.COMPANY_CAREER_PORTAL,
        ats=AtsKind.UN_CAREERS,
        status=KnowledgeStatus.ACTIVE,
    )


def test_un_careers_is_registered_as_inspira_portal() -> None:
    assert portal_for_id("un_careers") is UN_CAREERS
    catalog = fill_portal("un_careers")
    assert catalog is not None
    assert catalog.adapter == "inspira"
    assert "UN_SKILL_REG" in catalog.signup_url


def test_inspira_host_detects_as_un_careers() -> None:
    # Generic /psc/ paths are PeopleSoft; the UN Inspira host is UN Careers.
    assert detect_ats("https://hr.example.org/psc/ps/EMPLOYEE/HRMS/c/HRS_CE.GBL") is AtsKind.PEOPLESOFT
    assert detect_ats("https://inspira.un.org/psc/REGISTER/EMPLOYEE/HRMS/c/x") is AtsKind.UN_CAREERS
    assert detect_ats("https://careers.un.org/") is AtsKind.UN_CAREERS


def test_ats_needs_an_account_and_points_at_talent_pool() -> None:
    home = "https://careers.example.org/"
    target = signup_target(_site(home))

    assert target.need is AccountNeed.NEEDED
    assert "UN_SKILL_REG" in target.url


def test_registration_url_from_careers_home() -> None:
    assert "UN_SKILL_REG" in registration_url("https://careers.un.org/")


def test_sheet_fills_known_fields_and_never_password_or_subscribe() -> None:
    items = {item.label: item for item in signup_items(_candidate())}

    assert items["First Name"].value
    assert items["Email Address"].value
    assert items["LinkedIn"].value
    assert items["Password"].value == ""
    assert items["Subscribe"].value == ""
    assert items["Date of Birth"].value == ""
    assert items["Nationality"].value == ""


def test_render_sheet_uses_alias_never_raw_sst_email_when_alias_set() -> None:
    sheet = render_inspira_sheet(
        _candidate(),
        {"un-alias": "candidate+jobbot@example.org"},
        email_alias="un-alias",
    )
    assert "un_careers" in sheet
    assert "inspira" in sheet
    assert "un-alias → candidate+jobbot@example.org" in sheet
    assert "Password: needs_human" in sheet
    assert "Subscribe: needs_human" in sheet
    assert str(_candidate().personal.email) not in sheet


def test_recognize_signup_form_from_fixture() -> None:
    html = (FIXTURES / "signup.html").read_text(encoding="utf-8")
    status, form = recognize_signup_html(html, url=SIGNUP_URL)

    assert status is SignupRecognize.OK
    assert form is not None
    assert form.readable


def test_captcha_page_is_manual_challenge() -> None:
    html = (FIXTURES / "captcha.html").read_text(encoding="utf-8")
    status, form = recognize_signup_html(html, url=SIGNUP_URL)

    assert status is SignupRecognize.MANUAL_CHALLENGE
    assert form is None
    assert account_evidence(html) is AccountState.needs_human


def test_unrelated_page_is_ui_changed() -> None:
    html = (FIXTURES / "ui_changed.html").read_text(encoding="utf-8")
    status, _form = recognize_signup_html(html, url=SIGNUP_URL)

    assert status is SignupRecognize.UI_CHANGED


def test_candidate_home_fixture_is_evidenced() -> None:
    html = (FIXTURES / "candidate_home.html").read_text(encoding="utf-8")
    assert account_evidence(html) is AccountState.evidenced


def test_fill_plan_never_submits_and_skips_password() -> None:
    html = (FIXTURES / "signup.html").read_text(encoding="utf-8")
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
    assert "subscribe" in manual or "submit" in manual
