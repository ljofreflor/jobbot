"""Fill known signup fields from profile.yaml (HITL; no irreversible actions).

The fill driver lives here so signup.py can stay pure: no HTTP, no Playwright.
Stop before password, terms, CAPTCHA/2FA and final create/submit.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from playwright.sync_api import Page

from jobbot.browser.session import BrowserSession
from jobbot.companies.signup import AccountNeed, signup_sheet, signup_target
from jobbot.models.candidate import Candidate
from jobbot.portals.form_learn import (
    FieldKind,
    FormKnowledge,
    learn_form_page,
)

logger = logging.getLogger("jobbot.ats.signup")


@dataclass(frozen=True)
class SignupFillPlan:
    """What fields will be filled and what the candidate must do themselves."""

    url: str
    need: AccountNeed
    fields_to_fill: list[str]
    needs_manual: list[str]
    can_attach_cv: bool
    cv_path: Path | None


@dataclass(frozen=True)
class SignupFillResult:
    """What was actually filled (no submit, no password)."""

    plan: SignupFillPlan
    filled_fields: list[str]
    stopped_at: str


def build_fill_plan(
    candidate: Candidate,
    url: str,
    need: AccountNeed,
    form: FormKnowledge | None = None,
    cv_path: Path | None = None,
) -> SignupFillPlan:
    """What can be filled from profile.yaml and what requires HITL."""
    sheet = signup_sheet(candidate, form=form)
    fillable = [item.label for item in sheet if not item.yours_to_decide]
    manual = [
        "Password",
        "Terms and conditions",
        "CAPTCHA / 2FA if shown",
        "Final create/submit button",
    ]
    manual.extend(item.label for item in sheet if item.yours_to_decide)

    can_attach = cv_path is not None and cv_path.is_file() if cv_path else False

    return SignupFillPlan(
        url=url,
        need=need,
        fields_to_fill=fillable,
        needs_manual=manual,
        can_attach_cv=can_attach,
        cv_path=cv_path if can_attach else None,
    )


def fill_signup_form(
    page: Page,
    candidate: Candidate,
    form: FormKnowledge | None = None,
    cv_path: Path | None = None,
) -> SignupFillResult:
    """Fill known fields from profile.yaml. Stop before irreversible actions.

    Never fills: password, terms/consent checkboxes, submit buttons.
    May attach: CV if the path exists and a file input is found.
    """
    url = page.url
    logger.info("Filling signup form at %s", url)

    # Re-learn the form from the live page if not already known
    if form is None or not form.readable:
        form = learn_form_page(page)

    if not form.readable:
        logger.warning("Form is not readable; minimal fill will be attempted")

    # Get answers from the signup sheet
    sheet = signup_sheet(candidate, form=form)
    answers_map: dict[str, str] = {
        item.label.casefold(): item.value for item in sheet if item.value
    }
    filled: list[str] = []

    # Fill text/email/phone fields
    for field in form.fields if form.readable else []:
        if field.kind in {
            FieldKind.CHECKBOX,
            FieldKind.FILE,
        }:
            continue

        value = answers_map.get(field.label.casefold())
        if not value:
            continue

        # Never fill password fields
        if "password" in field.label.casefold() or "contraseña" in field.label.casefold():
            continue

        # Never fill fields that look like terms/consent
        if any(
            keyword in field.label.casefold()
            for keyword in ["terms", "términos", "consent", "consentimiento", "agree", "acepto"]
        ):
            continue

        try:
            # Try multiple selector strategies
            selectors = [
                f'[name="{field.name}"]',
                f'#{field.name}',
                f'[aria-label="{field.label}"]',
            ]

            filled_this = False
            for selector in selectors:
                try:
                    element = page.locator(selector).first
                    if element.count() > 0:
                        element.fill(value)
                        filled.append(field.label)
                        filled_this = True
                        logger.info("Filled %s", field.label)
                        break
                except Exception:
                    continue

            if not filled_this:
                logger.debug("Could not fill %s (field not found)", field.label)

        except Exception as e:
            logger.debug("Could not fill %s: %s", field.label, e)

    # Try to attach CV if a file input exists and path is valid
    if cv_path and cv_path.is_file():
        try:
            # Look for CV/Resume file inputs
            file_inputs = page.locator('input[type="file"]')
            if file_inputs.count() > 0:
                file_inputs.first.set_input_files(str(cv_path))
                filled.append("Resume/CV")
                logger.info("Attached CV: %s", cv_path)
        except Exception as e:
            logger.debug("Could not attach CV: %s", e)

    # Build mock site for signup_target
    from jobbot.companies.models import CareerSite, CareerSiteType, KnowledgeStatus
    from jobbot.portals.detect import AtsKind as AtsKindEnum

    mock_site = CareerSite(
        url=url,
        domain=url.split("//", 1)[-1].split("/", 1)[0],
        site_type=CareerSiteType.COMPANY_CAREER_PORTAL,
        ats=form.ats if form and form.ats else AtsKindEnum.UNKNOWN,
        status=KnowledgeStatus.CANDIDATE,
    )
    target_data = signup_target(mock_site)

    plan = build_fill_plan(candidate, url, target_data.need, form, cv_path)

    stopped_at = "Before password, terms, and submit"
    if not filled:
        stopped_at = "Could not fill any fields (form may need manual completion)"

    return SignupFillResult(
        plan=plan,
        filled_fields=filled,
        stopped_at=stopped_at,
    )


def fill_signup_with_session(
    session: BrowserSession,
    url: str,
    candidate: Candidate,
    form: FormKnowledge | None = None,
    cv_path: Path | None = None,
) -> SignupFillResult:
    """Open signup page, fill known fields, stop before irreversible actions."""
    page = session.page
    page.goto(url, wait_until="networkidle")

    # Wait for potential form render
    try:
        page.wait_for_selector("form, input, select, textarea", timeout=5000)
    except Exception:
        logger.debug("No form elements detected immediately")

    return fill_signup_form(page, candidate, form, cv_path)
