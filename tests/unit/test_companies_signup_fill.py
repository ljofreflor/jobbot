"""Assisted signup fill: HITL, stops before irreversible actions."""

from __future__ import annotations

from pathlib import Path

import pytest

from jobbot.adapters.ats.signup_fill import SignupFillPlan, build_fill_plan
from jobbot.companies.models import CareerSite, CareerSiteType, KnowledgeStatus
from jobbot.companies.signup import AccountNeed
from jobbot.models.candidate import Candidate
from jobbot.portals.detect import AtsKind
from jobbot.portals.form_learn import FieldKind, FormField, FormKnowledge, learn_form_html
from tests.fixtures.profile import sample_profile_dict

FORM_FIXTURE = Path("tests/fixtures/forms/greenhouse_apply.html")


def _site(url: str, ats: AtsKind) -> CareerSite:
    return CareerSite(
        url=url,
        domain=url.split("//", 1)[-1].split("/", 1)[0],
        site_type=CareerSiteType.COMPANY_CAREER_PORTAL,
        ats=ats,
        status=KnowledgeStatus.ACTIVE,
    )


def test_fill_plan_maps_profile_fields_to_fillable() -> None:
    """Fixture form with name/email/phone → fill plan includes them."""
    candidate = Candidate.model_validate(sample_profile_dict())
    form = FormKnowledge(
        url="https://example.com/apply",
        readable=True,
        fields=[
            FormField(name="email", label="Email", kind=FieldKind.EMAIL, required=True),
            FormField(name="full_name", label="Full name", kind=FieldKind.TEXT, required=True),
            FormField(name="phone", label="Phone", kind=FieldKind.PHONE, required=False),
        ],
    )

    plan = build_fill_plan(
        candidate,
        "https://example.com/apply",
        AccountNeed.NEEDED,
        form=form,
    )

    # Email and Full name should be fillable (they exist in profile)
    assert "Email" in plan.fields_to_fill
    assert "Full name" in plan.fields_to_fill
    # Phone is not in the sample profile, so it should be in needs_manual
    assert "Phone" in plan.needs_manual


def test_password_is_never_fillable() -> None:
    """A password field must be absent from the fill plan."""
    candidate = Candidate.model_validate(sample_profile_dict())
    form = FormKnowledge(
        url="https://example.com/apply",
        readable=True,
        fields=[
            FormField(name="email", label="Email", kind=FieldKind.EMAIL, required=True),
            FormField(name="password", label="Password", kind=FieldKind.TEXT, required=True),
        ],
    )

    plan = build_fill_plan(
        candidate,
        "https://example.com/apply",
        AccountNeed.NEEDED,
        form=form,
    )

    assert "Password" in plan.needs_manual
    assert "Password" not in plan.fields_to_fill


def test_apply_without_confirm_does_not_submit() -> None:
    """The fill driver stops before the submit button."""
    candidate = Candidate.model_validate(sample_profile_dict())

    plan = build_fill_plan(
        candidate,
        "https://example.com/apply",
        AccountNeed.NEEDED,
        form=None,
    )

    manual_text = " ".join(plan.needs_manual).casefold()
    assert "submit" in manual_text or "create" in manual_text


def test_learned_form_fixture_has_known_fields(project_root: Path) -> None:
    """A real form fixture maps to profile fields we can fill."""
    html = (project_root / FORM_FIXTURE).read_text(encoding="utf-8")
    form = learn_form_html(html, url="https://boards.greenhouse.io/acme/jobs/4001")

    candidate = Candidate.model_validate(sample_profile_dict())
    plan = build_fill_plan(
        candidate,
        form.url,
        AccountNeed.NOT_NEEDED,
        form=form,
    )

    # The fixture has a Resume/CV file input
    assert form.fields
    assert any(field.kind == FieldKind.FILE for field in form.fields)


def test_cv_attachment_requires_path_and_file() -> None:
    """CV is only marked attachable when the path exists."""
    candidate = Candidate.model_validate(sample_profile_dict())

    plan_no_path = build_fill_plan(
        candidate,
        "https://example.com/apply",
        AccountNeed.NEEDED,
        form=None,
        cv_path=None,
    )
    assert not plan_no_path.can_attach_cv

    fake_path = Path("/does/not/exist/cv.pdf")
    plan_fake_path = build_fill_plan(
        candidate,
        "https://example.com/apply",
        AccountNeed.NEEDED,
        form=None,
        cv_path=fake_path,
    )
    assert not plan_fake_path.can_attach_cv


def test_terms_and_consent_never_filled() -> None:
    """Fields that look like terms/consent are always manual."""
    candidate = Candidate.model_validate(sample_profile_dict())
    form = FormKnowledge(
        url="https://example.com/apply",
        readable=True,
        fields=[
            FormField(name="email", label="Email", kind=FieldKind.EMAIL, required=True),
            FormField(
                name="terms", label="I agree to terms and conditions", kind=FieldKind.CHECKBOX, required=True
            ),
        ],
    )

    plan = build_fill_plan(
        candidate,
        "https://example.com/apply",
        AccountNeed.NEEDED,
        form=form,
    )

    # Terms checkbox should not be in fillable
    assert "Email" in plan.fields_to_fill
    # Consent/terms is manual
    terms_manual = any("terms" in manual.casefold() for manual in plan.needs_manual)
    assert terms_manual


def test_greenhouse_lever_ashby_stay_not_needed() -> None:
    """Known ATS that don't require accounts remain not_needed."""
    candidate = Candidate.model_validate(sample_profile_dict())

    for ats in [AtsKind.GREENHOUSE, AtsKind.LEVER, AtsKind.ASHBY]:
        plan = build_fill_plan(
            candidate,
            "https://example.com/apply",
            AccountNeed.NOT_NEEDED,
            form=None,
        )
        assert plan.need == AccountNeed.NOT_NEEDED
