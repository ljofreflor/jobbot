"""Tests for cv sync: standing presence on permanent profiles + active company portals."""

from __future__ import annotations

from datetime import datetime, UTC
from pathlib import Path

import pytest

from jobbot.companies.models import (
    CareerSite,
    CareerSiteType,
    CompanyRecord,
    KnowledgeStatus,
    Observation,
    DiscoverySource,
)
from jobbot.companies.registry import CompanyRegistry
from jobbot.config import JobbotConfig
from jobbot.cv.sync import plan_sync, summarize_sync_plan, CompanyPortalTarget
from jobbot.models.candidate import Candidate
from jobbot.portals.detect import AtsKind
from tests.fixtures.profile import sample_profile_dict


def test_sync_plan_includes_permanent_profiles(tmp_path: Path) -> None:
    """Sync plan includes all permanent profiles (same as propagate)."""
    config = JobbotConfig(
        root=tmp_path,
        profile_path=tmp_path / "profile.yaml",
        templates_dir=tmp_path / "templates",
        output_dir=tmp_path / "output",
    )
    config.templates_dir.mkdir(parents=True)
    
    candidate = Candidate.model_validate(sample_profile_dict())
    registry = CompanyRegistry()
    
    plan = plan_sync(config, candidate, registry)
    
    # Should have permanent profiles: cv, getonboard, indeed, linkedin
    assert len(plan.permanent) == 4
    targets = {p.target.value for p in plan.permanent}
    assert "cv" in targets
    assert "getonboard" in targets
    assert "indeed" in targets
    assert "linkedin" in targets
    
    # No company portals yet
    assert len(plan.companies) == 0


def test_sync_plan_includes_active_company_portals(tmp_path: Path) -> None:
    """Active company portals appear in the plan."""
    config = JobbotConfig(
        root=tmp_path,
        profile_path=tmp_path / "profile.yaml",
        templates_dir=tmp_path / "templates",
        output_dir=tmp_path / "output",
    )
    config.templates_dir.mkdir(parents=True)
    
    candidate = Candidate.model_validate(sample_profile_dict())
    
    # Create registry with one active company portal
    registry = CompanyRegistry(
        companies=[
            CompanyRecord(
                id="betterfly",
                name="Betterfly",
                country="CL",
                sector="technology",
                domains=["betterfly.com"],
                career_sites=[
                    CareerSite(
                        url="https://betterfly.com/careers",
                        domain="betterfly.com",
                        site_type=CareerSiteType.COMPANY_CAREER_PORTAL,
                        ats=AtsKind.UNKNOWN,
                        status=KnowledgeStatus.ACTIVE,
                        first_seen=datetime(2026, 9, 1, 12, 0, 0, tzinfo=UTC),
                        last_verified=datetime(2026, 9, 1, 12, 0, 0, tzinfo=UTC),
                        observations=[
                            Observation(
                                source=DiscoverySource.USER_OBSERVATION,
                                checked_at=datetime(2026, 9, 1, 12, 0, 0, tzinfo=UTC),
                                ats=AtsKind.UNKNOWN,
                                site_type=CareerSiteType.COMPANY_CAREER_PORTAL,
                                evidence="career naming pattern",
                            )
                        ],
                    )
                ],
            )
        ]
    )
    
    plan = plan_sync(config, candidate, registry)
    
    # Should have company portals
    assert len(plan.companies) == 1
    assert plan.companies[0].company_name == "Betterfly"
    assert plan.companies[0].site_url == "https://betterfly.com/careers"
    assert plan.companies[0].ats == "unknown"


def test_sync_plan_excludes_candidate_portals(tmp_path: Path) -> None:
    """Candidate company portals do NOT appear in the plan."""
    config = JobbotConfig(
        root=tmp_path,
        profile_path=tmp_path / "profile.yaml",
        templates_dir=tmp_path / "templates",
        output_dir=tmp_path / "output",
    )
    config.templates_dir.mkdir(parents=True)
    
    candidate = Candidate.model_validate(sample_profile_dict())
    
    # Create registry with candidate and active portals
    registry = CompanyRegistry(
        companies=[
            CompanyRecord(
                id="betterfly",
                name="Betterfly",
                country="CL",
                sector="technology",
                domains=["betterfly.com"],
                career_sites=[
                    CareerSite(
                        url="https://betterfly.com/careers",
                        domain="betterfly.com",
                        site_type=CareerSiteType.COMPANY_CAREER_PORTAL,
                        ats=AtsKind.UNKNOWN,
                        status=KnowledgeStatus.ACTIVE,
                        first_seen=datetime(2026, 9, 1, 12, 0, 0, tzinfo=UTC),
                    )
                ],
            ),
            CompanyRecord(
                id="buk",
                name="Buk",
                country="CL",
                sector="technology",
                domains=["buk.cl"],
                career_sites=[
                    CareerSite(
                        url="https://buk.cl/careers",
                        domain="buk.cl",
                        site_type=CareerSiteType.COMPANY_CAREER_PORTAL,
                        ats=AtsKind.WORKDAY,
                        status=KnowledgeStatus.CANDIDATE,  # Not promoted yet
                        first_seen=datetime(2026, 9, 1, 12, 0, 0, tzinfo=UTC),
                    )
                ],
            ),
        ]
    )
    
    plan = plan_sync(config, candidate, registry)
    
    # Only active portal should be in plan (Betterfly)
    assert len(plan.companies) == 1
    assert plan.companies[0].company_name == "Betterfly"


def test_sync_plan_excludes_rejected_portals(tmp_path: Path) -> None:
    """Rejected company portals do NOT appear in the plan."""
    config = JobbotConfig(
        root=tmp_path,
        profile_path=tmp_path / "profile.yaml",
        templates_dir=tmp_path / "templates",
        output_dir=tmp_path / "output",
    )
    config.templates_dir.mkdir(parents=True)
    
    candidate = Candidate.model_validate(sample_profile_dict())
    
    # Create registry with active and rejected portals
    registry = CompanyRegistry(
        companies=[
            CompanyRecord(
                id="company-a",
                name="Company A",
                country="CL",
                domains=["company-a.cl"],
                career_sites=[
                    CareerSite(
                        url="https://company-a.cl/careers",
                        domain="company-a.cl",
                        site_type=CareerSiteType.COMPANY_CAREER_PORTAL,
                        ats=AtsKind.UNKNOWN,
                        status=KnowledgeStatus.ACTIVE,
                        first_seen=datetime(2026, 9, 1, 12, 0, 0, tzinfo=UTC),
                    )
                ],
            ),
            CompanyRecord(
                id="company-b",
                name="Company B",
                country="CL",
                domains=["company-b.cl"],
                career_sites=[
                    CareerSite(
                        url="https://company-b.cl/careers",
                        domain="company-b.cl",
                        site_type=CareerSiteType.COMPANY_CAREER_PORTAL,
                        ats=AtsKind.GREENHOUSE,
                        status=KnowledgeStatus.REJECTED,  # Rejected
                        first_seen=datetime(2026, 9, 1, 12, 0, 0, tzinfo=UTC),
                    )
                ],
            ),
        ]
    )
    
    plan = plan_sync(config, candidate, registry)
    
    # Only active portal should be in plan
    assert len(plan.companies) == 1
    assert plan.companies[0].company_name == "Company A"


def test_sync_dry_run_writes_nothing(tmp_path: Path) -> None:
    """Dry-run planning writes nothing and opens no browser."""
    config = JobbotConfig(
        root=tmp_path,
        profile_path=tmp_path / "profile.yaml",
        templates_dir=tmp_path / "templates",
        output_dir=tmp_path / "output",
    )
    config.templates_dir.mkdir(parents=True)
    
    candidate = Candidate.model_validate(sample_profile_dict())
    registry = CompanyRegistry(
        companies=[
            CompanyRecord(
                id="betterfly",
                name="Betterfly",
                country="CL",
                sector="technology",
                domains=["betterfly.com"],
                career_sites=[
                    CareerSite(
                        url="https://betterfly.com/careers",
                        domain="betterfly.com",
                        site_type=CareerSiteType.COMPANY_CAREER_PORTAL,
                        ats=AtsKind.UNKNOWN,
                        status=KnowledgeStatus.ACTIVE,
                        first_seen=datetime(2026, 9, 1, 12, 0, 0, tzinfo=UTC),
                    )
                ],
            )
        ]
    )
    
    # Planning should not write anything
    plan = plan_sync(config, candidate, registry)
    
    # Verify no output files were created
    assert not (config.output_dir / "base" / "cv.pdf").exists()
    assert not (config.output_dir / "base" / "cv.tex").exists()
    
    # But we have a plan
    assert plan.all_destinations > 0


def test_sync_plan_multiple_active_companies(tmp_path: Path) -> None:
    """Multiple active companies appear in the plan."""
    config = JobbotConfig(
        root=tmp_path,
        profile_path=tmp_path / "profile.yaml",
        templates_dir=tmp_path / "templates",
        output_dir=tmp_path / "output",
    )
    config.templates_dir.mkdir(parents=True)
    
    candidate = Candidate.model_validate(sample_profile_dict())
    
    # Create registry with multiple active company portals
    registry = CompanyRegistry(
        companies=[
            CompanyRecord(
                id="betterfly",
                name="Betterfly",
                country="CL",
                sector="technology",
                domains=["betterfly.com"],
                career_sites=[
                    CareerSite(
                        url="https://betterfly.com/careers",
                        domain="betterfly.com",
                        site_type=CareerSiteType.COMPANY_CAREER_PORTAL,
                        ats=AtsKind.UNKNOWN,
                        status=KnowledgeStatus.ACTIVE,
                        first_seen=datetime(2026, 9, 1, 12, 0, 0, tzinfo=UTC),
                    )
                ],
            ),
            CompanyRecord(
                id="notco",
                name="NotCo",
                country="CL",
                sector="technology",
                domains=["notco.com"],
                career_sites=[
                    CareerSite(
                        url="https://boards.greenhouse.io/notco",
                        domain="boards.greenhouse.io",
                        site_type=CareerSiteType.ATS_INSTANCE,
                        ats=AtsKind.GREENHOUSE,
                        status=KnowledgeStatus.ACTIVE,
                        first_seen=datetime(2026, 9, 2, 12, 0, 0, tzinfo=UTC),
                    )
                ],
            ),
            CompanyRecord(
                id="fintual",
                name="Fintual",
                country="CL",
                sector="technology",
                domains=["fintual.cl"],
                career_sites=[
                    CareerSite(
                        url="https://fintual.wd1.myworkdayjobs.com/Careers",
                        domain="fintual.wd1.myworkdayjobs.com",
                        site_type=CareerSiteType.ATS_INSTANCE,
                        ats=AtsKind.WORKDAY,
                        status=KnowledgeStatus.ACTIVE,
                        first_seen=datetime(2026, 9, 3, 12, 0, 0, tzinfo=UTC),
                    )
                ],
            ),
        ]
    )
    
    plan = plan_sync(config, candidate, registry)
    
    # Should have all 3 active company portals
    assert len(plan.companies) == 3
    company_names = {c.company_name for c in plan.companies}
    assert company_names == {"Betterfly", "NotCo", "Fintual"}


def test_summarize_sync_plan_empty() -> None:
    """Summary for empty plan."""
    from jobbot.cv.sync import SyncPlan
    
    plan = SyncPlan(permanent=[], companies=[])
    summary = summarize_sync_plan(plan)
    assert summary == "nothing to sync"


def test_summarize_sync_plan_with_destinations(tmp_path: Path) -> None:
    """Summary shows counts."""
    from jobbot.cv.sync import SyncPlan
    from jobbot.cv.propagate import TargetPlan, PropagationTarget
    
    plan = SyncPlan(
        permanent=[
            TargetPlan(
                target=PropagationTarget.CV,
                operations=["rebuild cv.pdf", "rebuild cv.tex"],
            ),
            TargetPlan(
                target=PropagationTarget.INDEED,
                operations=["update headline"],
            ),
        ],
        companies=[
            CompanyPortalTarget(
                company_id="betterfly",
                company_name="Betterfly",
                site_url="https://betterfly.com/careers",
                ats="unknown",
            ),
            CompanyPortalTarget(
                company_id="notco",
                company_name="NotCo",
                site_url="https://boards.greenhouse.io/notco",
                ats="greenhouse",
            ),
        ],
    )
    
    summary = summarize_sync_plan(plan)
    assert "2 permanent" in summary
    assert "2 company portals" in summary
