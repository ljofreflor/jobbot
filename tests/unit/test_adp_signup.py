"""ADP identity_bound account sheet (#436). Offline fixtures only."""

from __future__ import annotations

from pathlib import Path

import jobbot.adapters.alta_direccion.signup as signup_mod
from jobbot.adapters.alta_direccion.signup import (
    ADP,
    SignupRecognize,
    account_evidence,
    portal_for_id,
    recognize_signup_html,
    registration_url,
    render_adp_sheet,
    signup_items,
)
from jobbot.adapters.ats.signup_fill import build_fill_plan
from jobbot.companies.models import CareerSite, CareerSiteType, KnowledgeStatus
from jobbot.companies.signup import AccountNeed, signup_target
from jobbot.models.candidate import Candidate
from jobbot.portals.detect import AtsKind
from jobbot.portals.fill_catalog import fill_portal
from jobbot.portals.profile_state import AccountState
from tests.fixtures.profile import sample_profile_dict

FIXTURES = Path("tests/fixtures/alta_direccion")
SIGNUP_URL = "https://adp.example.org/concursos-spl/opencms/registro.html"


def _candidate() -> Candidate:
    return Candidate.model_validate(sample_profile_dict())


def _site(url: str) -> CareerSite:
    return CareerSite(
        url=url,
        domain=url.split("//", 1)[-1].split("/", 1)[0],
        site_type=CareerSiteType.COMPANY_CAREER_PORTAL,
        ats=AtsKind.ALTA_DIRECCION_PUBLICA,
        status=KnowledgeStatus.ACTIVE,
    )


def test_adp_is_registered_as_identity_bound() -> None:
    assert portal_for_id("adp") is ADP
    catalog = fill_portal("adp")
    assert catalog is not None
    assert catalog.adapter == "identity_bound"
    assert catalog.account is AccountState.identity_bound
    assert "registro.html" in catalog.signup_url


def test_ats_needs_an_account_and_points_at_registro() -> None:
    home = "https://adp.example.org/concursos-spl/opencms/"
    target = signup_target(_site(home))

    assert target.need is AccountNeed.NEEDED
    assert "registro.html" in target.url


def test_registration_url_from_login() -> None:
    login = "https://adp.example.org/concursos-spl/opencms/login.html"
    assert registration_url(login).endswith("registro.html")


def test_sheet_fills_known_fields_and_never_run_or_password() -> None:
    items = {item.label: item for item in signup_items(_candidate())}

    assert items["Nombre"].value
    assert items["Correo electrónico"].value
    assert items["RUN"].value == ""
    assert items["Contraseña"].value == ""
    assert items["Registrar"].value == ""


def test_render_sheet_uses_alias_never_raw_sst_email_when_alias_set() -> None:
    sheet = render_adp_sheet(
        _candidate(),
        {"adp-alias": "candidate+jobbot@example.org"},
        email_alias="adp-alias",
    )
    assert "adp" in sheet
    assert "identity_bound" in sheet
    assert "adp-alias → candidate+jobbot@example.org" in sheet
    assert "RUN: needs_human" in sheet
    assert "Registrar: needs_human" in sheet
    assert str(_candidate().personal.email) not in sheet


def test_identity_bound_never_imports_playwright() -> None:
    assert "playwright" not in signup_mod.__dict__
    render_adp_sheet(_candidate(), {})
    html = (FIXTURES / "signup.html").read_text(encoding="utf-8")
    recognize_signup_html(html, url=SIGNUP_URL)


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


def test_fill_plan_never_submits_and_skips_password_and_run() -> None:
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
    assert "contraseña" not in joined
    assert "run" not in joined
    manual = " ".join(plan.needs_manual).casefold()
    assert "contraseña" in manual or "password" in manual
    assert "run" in manual or "registrar" in manual
