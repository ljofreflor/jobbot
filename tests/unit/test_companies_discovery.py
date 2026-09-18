"""URL classification for company career platforms (evidence, never appearance)."""

from __future__ import annotations

from pathlib import Path

import pytest

from jobbot.companies.discovery import career_root_url, classify_url
from jobbot.companies.models import CareerSiteType
from jobbot.companies.urls import (
    PrivateRouteRejected,
    canonical_key,
    company_hint_from_url,
    public_url,
)
from jobbot.portals.detect import AtsKind, detect_ats, detect_ats_in_html


def test_public_url_drops_query_fragment_and_www() -> None:
    assert public_url("HTTPS://WWW.Empresa.cl/careers/?utm_source=x#top") == (
        "https://empresa.cl/careers"
    )
    assert canonical_key("https://empresa.cl/careers/") == canonical_key(
        "http://www.empresa.cl/careers?token=abc"
    )


def test_public_url_rejects_email_routes() -> None:
    with pytest.raises(PrivateRouteRejected):
        public_url("mailto:recruiter@example.com")


def test_corporate_career_path_stays_ats_unknown() -> None:
    """No ATS marker means unknown — JobBot never guesses by looks."""
    found = classify_url("https://empresa.cl/trabaja-con-nosotros")
    assert found.site_type == CareerSiteType.COMPANY_CAREER_PORTAL
    assert found.ats == AtsKind.UNKNOWN
    assert "career naming pattern" in found.evidence
    assert found.is_company_specific


def test_ats_instance_from_host_rule() -> None:
    found = classify_url("https://empresa.wd3.myworkdayjobs.com/en-US/External")
    assert found.site_type == CareerSiteType.ATS_INSTANCE
    assert found.ats == AtsKind.WORKDAY
    assert "host rule" in found.evidence


def test_new_ats_vendors_are_detected() -> None:
    assert detect_ats("https://empresa.teamtailor.com/jobs") == AtsKind.TEAMTAILOR
    assert detect_ats("https://apply.workable.com/empresa/") == AtsKind.WORKABLE
    assert detect_ats("https://empresa.recruitee.com/o/data-scientist") == AtsKind.RECRUITEE
    assert (
        detect_ats("https://career5.successfactors.eu/careers?company=empresa")
        == AtsKind.SUCCESSFACTORS
    )
    assert detect_ats("https://empresa.taleo.net/careersection/x") == AtsKind.ORACLE


def test_posting_url_collapses_to_portal_root() -> None:
    found = classify_url("https://boards.greenhouse.io/acme/jobs/4123456")
    assert found.site_type == CareerSiteType.JOB_POSTING
    assert found.ats == AtsKind.GREENHOUSE
    assert career_root_url(found.url, found.ats) == "https://boards.greenhouse.io/acme"


def test_workday_root_drops_locale_segment() -> None:
    url = "https://empresa.wd3.myworkdayjobs.com/en-US/External/job/Santiago/Data-Scientist_R-1"
    assert career_root_url(url, AtsKind.WORKDAY) == (
        "https://empresa.wd3.myworkdayjobs.com/External"
    )


def test_corporate_posting_collapses_to_parent_path() -> None:
    url = "https://empresa.cl/trabaja-con-nosotros/vacantes/data-scientist-senior"
    assert career_root_url(url) == "https://empresa.cl/trabaja-con-nosotros/vacantes"


def test_redirect_to_external_ats_is_recorded() -> None:
    """LinkedIn post → corporate page → Workday: keep both ends of the chain."""

    def resolver(url: str) -> str:
        return "https://empresa.wd3.myworkdayjobs.com/en-US/External"

    found = classify_url("https://empresa.cl/careers", resolve=True, resolver=resolver)
    assert found.ats == AtsKind.WORKDAY
    assert found.requested_url == "https://empresa.cl/careers"
    assert found.redirects_to == "https://empresa.wd3.myworkdayjobs.com/en-US/External"
    assert "redirect" in found.evidence
    assert career_root_url(found.url, found.ats) == (
        "https://empresa.wd3.myworkdayjobs.com/External"
    )


def test_html_marker_is_technical_evidence(project_root: Path) -> None:
    html = (project_root / "tests/fixtures/companies/career_page_greenhouse.html").read_text(
        encoding="utf-8"
    )
    kind, evidence = detect_ats_in_html(html)
    assert kind == AtsKind.GREENHOUSE
    assert "embed" in evidence
    found = classify_url("https://empresa.cl/trabaja-con-nosotros", html=html)
    assert found.ats == AtsKind.GREENHOUSE
    assert "html marker" in found.evidence


def test_job_boards_never_identify_a_company() -> None:
    for url in (
        "https://www.linkedin.com/jobs/view/123",
        "https://cl.indeed.com/viewjob?jk=abc",
        "https://www.getonbrd.com/jobs/data-scientist-empresa",
    ):
        found = classify_url(url)
        assert found.site_type == CareerSiteType.JOB_BOARD
        assert not found.is_company_specific


def test_company_hint_strips_career_prefixes() -> None:
    assert company_hint_from_url("https://trabajaenbci.cl") == "bci"
    assert company_hint_from_url("https://careers.empresa.cl/jobs") == "empresa"


def test_company_hint_on_ats_uses_tenant_not_vendor() -> None:
    """The employer is the board/tenant, never the ATS vendor."""
    assert company_hint_from_url("https://boards.greenhouse.io/acme/jobs/1") == "acme"
    assert company_hint_from_url("https://acme.wd3.myworkdayjobs.com/en-US/External") == "acme"
    assert company_hint_from_url("https://jobs.lever.co/acme/abc") == "acme"
    assert company_hint_from_url("https://acme.teamtailor.com/jobs") == "acme"
