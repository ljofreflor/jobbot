"""FAO Taleo account signup adapter (#447). Offline fixtures only."""

from __future__ import annotations

from pathlib import Path

from jobbot.adapters.ats.signup_fill import build_fill_plan
from jobbot.adapters.taleo.signup import (
    FAO,
    SignupRecognize,
    account_evidence,
    portal_for_id,
    portal_registration_url,
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
SIGNUP_URL = (
    "https://jobs.example.org/careersection/fao_external/accesscontrol.ftl?lang=es"
)
PRIVACY_URL = (
    "https://jobs.example.org/careersection/fao_external/privacyagreement/"
    "statementBeforeAuthentification.jsf"
)


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


def test_fao_is_registered_as_taleo_portal() -> None:
    assert portal_for_id("fao") is FAO
    catalog = fill_portal("fao")
    assert catalog is not None
    assert catalog.adapter == "taleo"
    assert "accesscontrol.ftl" in catalog.signup_url
    assert portal_registration_url(FAO) == FAO.signup_url


def test_fao_jobsearch_resolves_to_accesscontrol() -> None:
    jobsearch = (
        "https://jobs.example.org/careersection/fao_external/jobsearch.ftl?lang=es"
    )
    target = signup_target(_site(jobsearch))
    assert target.need is AccountNeed.NEEDED
    assert target.url == registration_url(jobsearch, lang="es")
    assert "accesscontrol.ftl" in target.url


def test_spanish_sheet_never_invents_password() -> None:
    items = {item.label: item for item in signup_items(_candidate(), portal=FAO)}
    assert items["Nombre"].value
    assert items["Correo Electrónico Personal"].value
    assert items["Contraseña"].value == ""
    assert items["Registrar"].value == ""
    assert items["Contraseña"].yours_to_decide


def test_render_fao_sheet_uses_alias() -> None:
    sheet = render_taleo_sheet(
        FAO,
        _candidate(),
        {"fao-alias": "candidate+jobbot@example.org"},
        email_alias="fao-alias",
    )
    assert "fao" in sheet
    assert "fao_external" in sheet
    assert "fao-alias → candidate+jobbot@example.org" in sheet
    assert "Contraseña: needs_human" in sheet
    assert str(_candidate().personal.email) not in sheet


def test_recognize_fao_signup_form() -> None:
    html = (FIXTURES / "fao_signup.html").read_text(encoding="utf-8")
    status, form = recognize_signup_html(html, url=SIGNUP_URL)
    assert status is SignupRecognize.OK
    assert form is not None
    labels = {field.label.casefold() for field in form.fields}
    assert any("correo" in label for label in labels)


def test_privacy_wall_is_manual_challenge_never_auto_accept() -> None:
    html = (FIXTURES / "fao_privacy_wall.html").read_text(encoding="utf-8")
    status, form = recognize_signup_html(html, url=PRIVACY_URL)
    assert status is SignupRecognize.MANUAL_CHALLENGE
    assert form is None
    assert account_evidence(html, url=PRIVACY_URL) is AccountState.needs_human


def test_fill_plan_skips_password_and_never_submits() -> None:
    html = (FIXTURES / "fao_signup.html").read_text(encoding="utf-8")
    _, form = recognize_signup_html(html, url=SIGNUP_URL)
    assert form is not None
    plan = build_fill_plan(_candidate(), SIGNUP_URL, AccountNeed.NEEDED, form=form)
    assert plan.will_submit is False
    assert "password" not in " ".join(plan.fields_to_fill).casefold()
    assert "contraseña" not in " ".join(plan.fields_to_fill).casefold()
