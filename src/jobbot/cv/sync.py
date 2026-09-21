"""Standing presence sync: permanent profiles + active company portals (issue #43).

``cv sync`` plans permanent destinations the same way ``cv propagate`` does, and adds
read-only rows for every *active* career site in the local companies registry.
Company portal writes and signup ``--apply`` fill are later slices of #43 / #44 —
this module never opens a browser for those rows.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from jobbot.browser.sessions import SessionState
from jobbot.companies.models import CareerSite, CompanyRecord, KnowledgeStatus
from jobbot.companies.registry import (
    CompanyRegistry,
    active_career_sites,
    default_companies_path,
    load_companies,
)
from jobbot.companies.signup import AccountNeed, signup_target
from jobbot.config import JobbotConfig
from jobbot.cv.propagate import TargetPlan, plan_propagation
from jobbot.models.candidate import Candidate
from jobbot.portals.detect import AtsKind


@dataclass(frozen=True)
class CompanySyncRow:
    """One active company career site in the sync plan (plan-only today)."""

    company_id: str
    company_name: str
    url: str
    ats: AtsKind
    need: AccountNeed
    action: str
    hint: str

    @property
    def destination(self) -> str:
        return f"{self.company_id}:{self.ats.value}"


@dataclass(frozen=True)
class SyncPlan:
    """Permanent TargetPlans plus active-company rows (never written by this module)."""

    permanent: list[TargetPlan]
    companies: list[CompanySyncRow]


def plan_sync(
    config: JobbotConfig,
    candidate: Candidate,
    *,
    section: str = "all",
    sessions: Sequence[SessionState] | None = None,
    cdp_url: str | None = None,
    registry: CompanyRegistry | None = None,
) -> SyncPlan:
    """Build the standing-presence plan: permanentes + active companies."""
    permanent = plan_propagation(
        config,
        candidate,
        section=section,
        sessions=sessions,
        cdp_url=cdp_url,
    )
    companies = plan_active_companies(config, registry=registry)
    return SyncPlan(permanent=permanent, companies=companies)


def plan_active_companies(
    config: JobbotConfig,
    *,
    registry: CompanyRegistry | None = None,
) -> list[CompanySyncRow]:
    """Active career sites only — candidates and rejected never appear."""
    reg = registry if registry is not None else _load_registry(config)
    rows: list[CompanySyncRow] = []
    for record, site in active_career_sites(reg, include_candidates=False):
        if site.status != KnowledgeStatus.ACTIVE:
            continue
        rows.append(_row_for(record, site))
    return rows


def _load_registry(config: JobbotConfig) -> CompanyRegistry:
    return load_companies(default_companies_path(config.root))


def _row_for(record: CompanyRecord, site: CareerSite) -> CompanySyncRow:
    target = signup_target(site)
    if target.need == AccountNeed.NEEDED:
        action = "needs_account"
        hint = (
            f"jobbot companies signup {record.name}  "
            "(sheet today; fill --apply is #44; portal write is #43)"
        )
    elif target.need == AccountNeed.NOT_NEEDED:
        action = "update_profile"
        hint = (
            "no standing account — apply per vacancy with "
            "`jobbot application apply Jxxxx` (company write via cv sync is #43)"
        )
    else:
        action = "blocked"
        hint = (
            f"jobbot companies signup {record.name}  "
            "(unknown whether an account is required; open and look)"
        )
    return CompanySyncRow(
        company_id=record.id,
        company_name=record.name,
        url=site.url,
        ats=site.ats,
        need=target.need,
        action=action,
        hint=hint,
    )
