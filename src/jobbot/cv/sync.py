"""CV sync: standing presence on permanent profiles + active company portals.

Extends propagation by including active company career sites from the collaborative base.
Planning is read-only and browser-free. Writes target permanent portals only (--apply HITL);
company career-site writes remain plan-only until an adapter exists.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field

from jobbot.companies.models import KnowledgeStatus
from jobbot.companies.registry import CompanyRegistry, active_career_sites
from jobbot.config import JobbotConfig
from jobbot.cv.propagate import (
    DEFAULT_TARGETS,
    BROWSER_TARGETS,
    PropagationTarget,
    TargetPlan,
    plan_cv,
    plan_getonboard,
    plan_indeed,
    plan_linkedin,
    with_session,
)
from jobbot.models.candidate import Candidate
from jobbot.browser.sessions import SessionState, session_for


@dataclass(frozen=True)
class CompanyPortalTarget:
    """A company career site included in the sync plan."""

    company_id: str
    company_name: str
    site_url: str
    ats: str
    note: str | None = None


@dataclass(frozen=True)
class SyncPlan:
    """Full sync plan: permanent profiles + active company portals."""

    permanent: list[TargetPlan] = field(default_factory=list)
    companies: list[CompanyPortalTarget] = field(default_factory=list)

    @property
    def all_destinations(self) -> int:
        """Total number of sync destinations."""
        return len(self.permanent) + len(self.companies)

    @property
    def permanent_ready(self) -> list[TargetPlan]:
        """Permanent profiles ready for --apply."""
        return [p for p in self.permanent if p.ready]


def plan_sync(
    config: JobbotConfig,
    candidate: Candidate,
    registry: CompanyRegistry,
    *,
    section: str = "all",
    sessions: Sequence[SessionState] | None = None,
    cdp_url: str | None = None,
) -> SyncPlan:
    """Plan CV sync: permanent profiles + active company portals.

    Args:
        config: JobBot configuration
        candidate: The candidate profile
        registry: Company registry for active portals
        section: For Indeed sync (headline, summary, skills, experience, all)
        sessions: Browser session states for preflight
        cdp_url: Optional Chrome DevTools Protocol URL

    Returns:
        SyncPlan with permanent profiles and company portals
    """
    # Plan permanent profiles (existing propagation targets)
    permanent_plans: list[TargetPlan] = []
    for target in DEFAULT_TARGETS:
        if target == PropagationTarget.CV:
            permanent_plans.append(plan_cv(config, candidate))
        elif target == PropagationTarget.INDEED:
            permanent_plans.append(plan_indeed(config, candidate, section=section))
        elif target == PropagationTarget.LINKEDIN:
            permanent_plans.append(plan_linkedin(config, candidate))
        elif target == PropagationTarget.GETONBOARD:
            permanent_plans.append(plan_getonboard(config, candidate))

    # Fold browser session state into plans
    if sessions is not None:
        permanent_plans = [
            with_session(plan, session_for(sessions, plan.target.value), cdp_url=cdp_url)
            if plan.target in BROWSER_TARGETS
            else plan
            for plan in permanent_plans
        ]

    # Add active company portals (never candidate or rejected)
    company_targets: list[CompanyPortalTarget] = []
    for company, site in active_career_sites(registry, include_candidates=False):
        # Only include sites with active status
        if site.status != KnowledgeStatus.ACTIVE:
            continue

        note = None
        # Check if we have an adapter for this ATS (placeholder for future)
        # For now, all company portals are plan-only
        if site.ats.value == "unknown":
            note = "ATS unknown; adapter needed for writes"
        else:
            note = f"adapter for {site.ats.value} needed for writes"

        company_targets.append(
            CompanyPortalTarget(
                company_id=company.id,
                company_name=company.name,
                site_url=site.url,
                ats=site.ats.value,
                note=note,
            )
        )

    return SyncPlan(permanent=permanent_plans, companies=company_targets)


def summarize_sync_plan(plan: SyncPlan) -> str:
    """One-line summary for narration."""
    perm_count = len([p for p in plan.permanent if p.actionable])
    comp_count = len(plan.companies)
    
    if perm_count == 0 and comp_count == 0:
        return "nothing to sync"
    
    parts = []
    if perm_count > 0:
        parts.append(f"{perm_count} permanent")
    if comp_count > 0:
        parts.append(f"{comp_count} company portals")
    
    blocked = [p for p in plan.permanent if not p.ready]
    if blocked:
        parts.append(f"blocked: {', '.join(p.target.value for p in blocked)}")
    
    return "; ".join(parts)
