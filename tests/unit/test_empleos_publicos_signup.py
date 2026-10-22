"""Empleos Públicos identity_bound account sheet (#435). Offline fixtures only."""

from __future__ import annotations

from pathlib import Path

import jobbot.adapters.empleospublicos.signup as signup_mod
from jobbot.adapters.ats.signup_fill import build_fill_plan
from jobbot.adapters.empleospublicos.signup import (
    EMPLEOS_PUBLICOS,
    SignupRecognize,
    account_evidence,
    portal_for_id,
    recognize_signup_html,
    registration_url,
    render_empleos_publicos_sheet,
    signup_items,
)
from jobbot.companies.models import CareerSite, CareerSiteType, KnowledgeStatus
from jobbot.companies.signup import AccountNeed, signup_target
from jobbot.models.candidate import Candidate
from jobbot.portals.detect import AtsKind
from jobbot.portals.fill_catalog import fill_portal
from jobbot.portals.profile_state import AccountState
from tests.fixtures.profile import sample_profile_dict

FIXTURES = Path("tests/fixtures/empleospublicos")
SIGNUP_URL = (
    "https://example-careers.example.org/pub/usuarios/usrPostulanteAgregar.aspx"
)


def _candidate() -> Candidate:
    return Candidate.model_validate(sample_profile_dict())


def _site(url: str) -> CareerSite:
    return CareerSite(
        url=url,
        domain=url.split("//", 1)[-1].split("/", 1)[0],
        site_type=CareerSiteType.COMPANY_CAREER_PORTAL,
        ats=AtsKind.EMPLEOS_PUBLICOS,
        status=KnowledgeStatus.ACTIVE,
    )


def test_empleos_publicos_is_registered_as_identity_bound() -> None:
    assert portal_for_id("empleos_publicos") is EMPLEOS_PUBLICOS
    catalog = fill_portal("empleos_publicos")
    assert catalog is not None
    assert catalog.adapter == "identity_bound"
    assert catalog.account is AccountState.identity_bound
    assert "usrPostulanteAgregar" in catalog.signup_url


def test_ats_needs_an_account_and_points_at_registration() -> None:
    home = "https://example-careers.example.org/"
    target = signup_target(_site(home))

    assert target.need is AccountNeed.NEEDED
    assert "usrPostulanteAgregar" in target.url


def test_registration_url_from_login() -> None:
    login = "https://example-careers.example.org/pub/usuarios/usrLogin.aspx"
    assert "usrPostulanteAgregar" in registration_url(login)


def test_sheet_fills_known_fields_and_never_run_or_password() -> None:
    items = {item.label: item for item in signup_items(_candidate())}

    assert items["Nombres"].value
    assert items["Correo electrónico"].value
    assert items["RUN"].value == ""
    assert items["RUN"].yours_to_decide
    assert items["Contraseña"].value == ""
    assert items["ClaveÚnica"].value == ""
    assert items["Crear cuenta"].value == ""


def test_render_sheet_uses_alias_never_raw_sst_email_when_alias_set() -> None:
    sheet = render_empleos_publicos_sheet(
        _candidate(),
        {"ep-alias": "candidate+jobbot@example.org"},
        email_alias="ep-alias",
    )
    assert "empleos_publicos" in sheet
    assert "identity_bound" in sheet
    assert "ep-alias → candidate+jobbot@example.org" in sheet
    assert "RUN: needs_human" in sheet
    assert "ClaveÚnica: needs_human" in sheet
    assert "Crear cuenta: needs_human" in sheet
    assert str(_candidate().personal.email) not in sheet


def test_identity_bound_never_imports_playwright() -> None:
    """Sheet / recognition path must not pull a browser driver (#435)."""
    assert "playwright" not in signup_mod.__dict__
    # Calling sheet helpers must stay import-safe without Playwright.
    render_empleos_publicos_sheet(_candidate(), {})
    html = (FIXTURES / "signup.html").read_text(encoding="utf-8")
    recognize_signup_html(html, url=SIGNUP_URL)


def test_recognize_signup_form_from_fixture() -> None:
    html = (FIXTURES / "signup.html").read_text(encoding="utf-8")
    status, form = recognize_signup_html(html, url=SIGNUP_URL)

    assert status is SignupRecognize.OK
    assert form is not None
    assert form.readable


def test_claveunica_gate_is_manual_challenge() -> None:
    html = (FIXTURES / "claveunica_gate.html").read_text(encoding="utf-8")
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
    assert "run" in manual or "crear" in manual
