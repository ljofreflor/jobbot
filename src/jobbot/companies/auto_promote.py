"""Which candidate career sites technical evidence can promote.

Usage and imported trust are not signals here. HTTP 200 alone is not evidence.
Rejected, stale, and job-board rows never qualify.
"""

from __future__ import annotations

import re

from jobbot.companies.models import CareerSite, CareerSiteType, CompanyRecord, KnowledgeStatus
from jobbot.companies.registry import CompanyRegistry
from jobbot.portals.detect import AtsKind

_HTTP_ONLY = re.compile(r"^(?:https?\s+)?(?:status\s+)?200\b", re.I)


def has_technical_evidence(site: CareerSite) -> bool:
    """A known ATS, or an observation that says more than an HTTP status."""
    if site.ats is not AtsKind.UNKNOWN:
        return True
    return any(_substantive(obs.evidence) for obs in site.observations)


def auto_promote_eligible(site: CareerSite) -> bool:
    """True when a dry-run may offer this site, and ``--apply`` may mark it active."""
    if site.status is not KnowledgeStatus.CANDIDATE:
        return False
    if site.site_type is CareerSiteType.JOB_BOARD:
        return False
    if site.conflicts:
        return False
    return has_technical_evidence(site)


def auto_promote_plan(registry: CompanyRegistry) -> tuple[tuple[CompanyRecord, CareerSite], ...]:
    """Eligible sites, ordered by company id then URL."""
    rows = [
        (record, site)
        for record in registry.companies
        for site in record.career_sites
        if auto_promote_eligible(site)
    ]
    rows.sort(key=lambda pair: (pair[0].id, pair[1].url))
    return tuple(rows)


def _substantive(evidence: str) -> bool:
    text = " ".join(evidence.split())
    if not text:
        return False
    return _HTTP_ONLY.match(text) is None
