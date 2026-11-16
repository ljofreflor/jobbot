"""Saved company sites are re-read with today's offline detectors."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from rich.console import Console

from jobbot.companies.models import CareerSiteType, DiscoverySource, KnowledgeStatus
from jobbot.companies.recheck import apply_recheck, plan_recheck
from jobbot.companies.registry import CompanyRegistry, default_companies_path, save_companies
from jobbot.exit_codes import SUCCESS, VALIDATION_FAILURE
from jobbot.portals.detect import AtsKind

POSTING = "https://careers.empresa-demo.cl/global/en/job/fe3426f378a7100/Un-Cargo"
ROOT = "https://careers.empresa-demo.cl/global/en"
MANATAL = "https://careers-page.com/empresa-demo"
LEVER = "https://jobs.lever.co/empresa-demo"
BOARD = "https://cl.indeed.com/viewjob"


def _seed(
    registry: CompanyRegistry,
    *,
    company: str,
    url: str,
    ats: AtsKind = AtsKind.UNKNOWN,
    site_type: CareerSiteType = CareerSiteType.UNKNOWN,
    status: KnowledgeStatus = KnowledgeStatus.CANDIDATE,
) -> None:
    registry.observe(
        company=company,
        url=url,
        source=DiscoverySource.USER_OBSERVATION,
        site_type=site_type,
        ats=ats,
        evidence="stored earlier",
        status=status if status == KnowledgeStatus.ACTIVE else None,
    )
    if status == KnowledgeStatus.REJECTED:
        registry.reject(company, url=url)
    elif status == KnowledgeStatus.ACTIVE:
        registry.promote(company, url=url)


def test_posting_dry_run_proposes_the_root_and_writes_nothing(tmp_path: Path) -> None:
    registry = CompanyRegistry()
    _seed(
        registry,
        company="Empresa Demo",
        url=POSTING,
        site_type=CareerSiteType.JOB_POSTING,
    )
    path = default_companies_path(tmp_path)
    save_companies(registry, path)
    before = path.read_bytes()

    changes = plan_recheck(registry)

    assert path.read_bytes() == before
    assert [change.action for change in changes] == ["add_root", "reject_posting"]
    assert changes[0].root_url == ROOT
    assert registry.companies[0].career_sites[0].status == KnowledgeStatus.CANDIDATE


def test_apply_rejects_the_posting_and_keeps_the_portal_root() -> None:
    registry = CompanyRegistry()
    _seed(
        registry,
        company="Empresa Demo",
        url=POSTING,
        site_type=CareerSiteType.JOB_POSTING,
    )

    apply_recheck(registry, plan_recheck(registry))
    record = registry.companies[0]
    posting = record.find_site(POSTING)
    root = record.find_site(ROOT)

    assert posting is not None and posting.status == KnowledgeStatus.REJECTED
    assert root is not None
    assert root.url == ROOT
    assert "fe3426f378a7100" not in root.url


def test_unknown_manatal_host_gains_a_host_rule_observation_and_is_promoted() -> None:
    registry = CompanyRegistry()
    _seed(
        registry,
        company="Empresa Demo",
        url=MANATAL,
        site_type=CareerSiteType.ATS_INSTANCE,
    )

    apply_recheck(registry, plan_recheck(registry))
    site = registry.companies[0].find_site(MANATAL)

    assert site is not None
    assert site.ats == AtsKind.MANATAL
    assert site.status == KnowledgeStatus.ACTIVE
    fresh = site.observations[-1]
    assert fresh.ats == AtsKind.MANATAL
    assert "host rule" in fresh.evidence
    assert site.observations[0].evidence == "stored earlier"


def test_contradicting_host_rule_leaves_the_site_stale_with_both_evidences() -> None:
    registry = CompanyRegistry()
    _seed(
        registry,
        company="Empresa Demo",
        url=LEVER,
        ats=AtsKind.GREENHOUSE,
        site_type=CareerSiteType.ATS_INSTANCE,
        status=KnowledgeStatus.ACTIVE,
    )

    apply_recheck(registry, plan_recheck(registry))
    site = registry.companies[0].find_site(LEVER)

    assert site is not None
    assert site.ats == AtsKind.GREENHOUSE
    assert site.status == KnowledgeStatus.STALE
    assert {obs.ats for obs in site.observations} >= {AtsKind.GREENHOUSE, AtsKind.LEVER}
    assert site.conflicts


def test_rejected_site_is_left_alone() -> None:
    registry = CompanyRegistry()
    _seed(
        registry,
        company="Empresa Demo",
        url=MANATAL,
        status=KnowledgeStatus.REJECTED,
    )
    before = len(registry.companies[0].career_sites[0].observations)

    assert plan_recheck(registry) == []
    assert registry.companies[0].career_sites[0].status == KnowledgeStatus.REJECTED
    assert len(registry.companies[0].career_sites[0].observations) == before


def test_job_board_is_marked_for_review_and_not_deleted() -> None:
    registry = CompanyRegistry()
    _seed(
        registry,
        company="Empresa Demo",
        url=BOARD,
        site_type=CareerSiteType.COMPANY_CAREER_PORTAL,
        status=KnowledgeStatus.ACTIVE,
    )

    apply_recheck(registry, plan_recheck(registry))
    sites = registry.companies[0].career_sites

    assert len(sites) == 1
    assert sites[0].status != KnowledgeStatus.REJECTED
    assert sites[0].notes is not None and "review: job board" in sites[0].notes


def test_a_second_apply_does_not_duplicate_observations_or_sites() -> None:
    registry = CompanyRegistry()
    _seed(registry, company="Empresa Demo", url=POSTING, site_type=CareerSiteType.JOB_POSTING)
    _seed(registry, company="Empresa Demo", url=MANATAL, site_type=CareerSiteType.ATS_INSTANCE)
    _seed(
        registry,
        company="Empresa Demo",
        url=LEVER,
        ats=AtsKind.GREENHOUSE,
        site_type=CareerSiteType.ATS_INSTANCE,
    )

    apply_recheck(registry, plan_recheck(registry))
    counts = {site.url: len(site.observations) for site in registry.companies[0].career_sites}
    site_count = len(registry.companies[0].career_sites)

    assert plan_recheck(registry) == []
    apply_recheck(registry, plan_recheck(registry))
    assert len(registry.companies[0].career_sites) == site_count
    assert {
        site.url: len(site.observations) for site in registry.companies[0].career_sites
    } == counts


def test_cli_dry_run_does_not_change_the_file(
    tmp_path: Path, project_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "profile.yaml").write_text(
        (project_root / "data" / "profile.example.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    registry = CompanyRegistry()
    _seed(registry, company="Empresa Demo", url=POSTING, site_type=CareerSiteType.JOB_POSTING)
    path = default_companies_path(tmp_path)
    save_companies(registry, path)
    before = path.read_bytes()
    import jobbot.cli as cli

    buffer = io.StringIO()
    monkeypatch.setattr(cli, "console", Console(file=buffer, color_system=None))

    assert cli.run_cli(["companies", "recheck"], standalone_mode=False) == SUCCESS

    assert path.read_bytes() == before
    assert "add_root" in buffer.getvalue()
    assert "Dry-run only" in buffer.getvalue()


def test_learn_on_an_active_site_does_not_say_candidate_stored(
    tmp_path: Path, project_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "profile.yaml").write_text(
        (project_root / "data" / "profile.example.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    registry = CompanyRegistry()
    _seed(
        registry,
        company="Acme",
        url="https://boards.greenhouse.io/acme",
        ats=AtsKind.GREENHOUSE,
        site_type=CareerSiteType.ATS_INSTANCE,
        status=KnowledgeStatus.ACTIVE,
    )
    save_companies(registry, default_companies_path(tmp_path))
    import jobbot.cli as cli

    buffer = io.StringIO()
    monkeypatch.setattr(cli, "console", Console(file=buffer, color_system=None))

    code = cli.run_cli(
        ["companies", "learn", "https://boards.greenhouse.io/acme", "--company", "Acme"],
        standalone_mode=False,
    )

    assert code == SUCCESS
    text = buffer.getvalue()
    assert "Candidate stored" not in text
    assert "active" in text


def test_recheck_unknown_company_exits(
    tmp_path: Path, project_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "profile.yaml").write_text(
        (project_root / "data" / "profile.example.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    save_companies(CompanyRegistry(), default_companies_path(tmp_path))
    import jobbot.cli as cli

    assert (
        cli.run_cli(["companies", "recheck", "nadie"], standalone_mode=False) == VALIDATION_FAILURE
    )
