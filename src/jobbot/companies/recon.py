"""Inside recon: learn ATS and form questions by reading a page the human is on.

This is the return path of the oneshot: the outside scan finds candidate URLs, but
the **component truth** (ATS kind, registration fields, where a CV uploads) is learned
by entering. The human completes irreversible steps (password, terms, CAPTCHA); JobBot
observes the page they reached and stores technical evidence only.

No invented passwords, no terms, no CAPTCHA bypass, no final account creation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from jobbot.companies.models import (
    CareerSiteType,
    DiscoverySource,
    Observation,
    utc_now,
)
from jobbot.portals.detect import AtsKind, detect_ats_in_html
from jobbot.portals.form_learn import FormKnowledge, learn_form_html


@dataclass(frozen=True)
class ReconResult:
    """What recon learned from the page the human is on."""

    company_id: str
    url: str
    ats: AtsKind
    ats_evidence: str
    form: FormKnowledge
    observation_written: bool = False
    form_written: bool = False


def recon_from_html(
    html: str,
    *,
    url: str,
    company: str,
    company_id: str | None = None,
) -> ReconResult:
    """Learn ATS and form questions from HTML. Pure: no network, no writes.

    ATS detection requires technical evidence (host rule, redirect, or embedded
    marker) — never guess from hostname alone. Form knowledge stores
    labels/types/required/options/accept only; no typed values, tokens, or
    example emails.
    """
    ats, ats_evidence = detect_ats_in_html(html)
    form = learn_form_html(html, url=url, company=company, ats=ats)

    return ReconResult(
        company_id=company_id or company.lower().replace(" ", "-"),
        url=url,
        ats=ats,
        ats_evidence=ats_evidence,
        form=form,
    )


def recon_from_fixture(
    fixture_path: Path,
    *,
    url: str,
    company: str,
    company_id: str | None = None,
) -> ReconResult:
    """Learn from a saved HTML fixture (for tests and offline inspection)."""
    html = fixture_path.read_text(encoding="utf-8")
    return recon_from_html(html, url=url, company=company, company_id=company_id)


def make_observation(result: ReconResult) -> Observation:
    """Build an observation from recon results (never writes)."""
    return Observation(
        source=DiscoverySource.USER_OBSERVATION,
        checked_at=utc_now(),
        ats=result.ats,
        site_type=CareerSiteType.COMPANY_CAREER_PORTAL,
        evidence=result.ats_evidence,
        observed_url=result.url,
    )
