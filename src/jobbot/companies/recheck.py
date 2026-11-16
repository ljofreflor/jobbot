"""Re-run today's offline detectors on sites already stored in the registry.

A saved classification is the detector of the day it was learned. Host rules and
career-root collapsing move on; this pass proposes what the current detectors
would record, as a new observation. It never fetches a page and never deletes a
site.
"""

from __future__ import annotations

from dataclasses import dataclass

from jobbot.companies.discovery import career_root_url, classify_url
from jobbot.companies.models import (
    CareerSite,
    CareerSiteType,
    CompanyRecord,
    DiscoverySource,
    KnowledgeStatus,
)
from jobbot.companies.registry import CompanyRegistry
from jobbot.companies.urls import canonical_key
from jobbot.portals.detect import JOB_BOARD_KINDS, AtsKind, is_white_label_tenant

REVIEW_NOTE = "review: job board"


@dataclass(frozen=True)
class RecheckChange:
    """One proposed registry edit. ``detail`` is the reason shown to the operator."""

    company_id: str
    url: str
    action: str
    detail: str
    root_url: str = ""
    ats: AtsKind = AtsKind.UNKNOWN
    site_type: CareerSiteType = CareerSiteType.UNKNOWN
    evidence: str = ""


def plan_recheck(
    registry: CompanyRegistry,
    *,
    company: str | None = None,
) -> list[RecheckChange]:
    """What the current offline detectors would record. Does not write."""
    records = registry.companies
    if company is not None:
        found = registry.find_company(company)
        records = [found] if found is not None else []
    changes: list[RecheckChange] = []
    for record in records:
        for site in record.career_sites:
            changes.extend(_proposals(record, site))
    return changes


def apply_recheck(registry: CompanyRegistry, changes: list[RecheckChange]) -> int:
    """Apply an already confirmed list. Returns how many edits landed."""
    applied = 0
    for change in changes:
        record = registry.find_company(change.company_id)
        if record is None:
            continue
        if change.action == "add_root" and change.root_url:
            registry.observe(
                company=record.name,
                company_id=record.id,
                url=change.root_url,
                source=DiscoverySource.RECHECK,
                site_type=change.site_type,
                ats=change.ats,
                evidence=change.evidence,
            )
            applied += 1
        elif change.action == "reject_posting":
            if registry.reject(record.id, url=change.url) is not None:
                applied += 1
        elif change.action == "observe":
            registry.observe(
                company=record.name,
                company_id=record.id,
                url=change.url,
                source=DiscoverySource.RECHECK,
                site_type=change.site_type,
                ats=change.ats,
                evidence=change.evidence,
            )
            applied += 1
        elif change.action == "mark_review":
            site = record.find_site(change.url)
            if site is not None and REVIEW_NOTE not in (site.notes or ""):
                site.notes = f"{site.notes}; {REVIEW_NOTE}" if site.notes else REVIEW_NOTE
                applied += 1
        elif change.action == "promote":
            site = record.find_site(change.url)
            if (
                site is not None
                and site.status == KnowledgeStatus.CANDIDATE
                and (site.ats not in JOB_BOARD_KINDS or is_white_label_tenant(site.url))
                and site.ats != AtsKind.UNKNOWN
                and registry.promote(record.id, url=site.url)
            ):
                applied += 1
    return applied


def _proposals(record: CompanyRecord, site: CareerSite) -> list[RecheckChange]:
    if site.status == KnowledgeStatus.REJECTED:
        return []
    current = classify_url(site.url)
    root = career_root_url(current.url, current.ats)
    if canonical_key(root) != site.key:
        return _posting_proposals(record, site, root)
    # A company tenant (acme.trabajando.cl) runs on a board's software; it is still its site.
    board = current.site_type == CareerSiteType.JOB_BOARD or current.ats in JOB_BOARD_KINDS
    if board and not is_white_label_tenant(current.url):
        return _board_proposals(record, site, current.ats, current.evidence)
    return _ats_proposals(record, site, current.ats, current.site_type, current.evidence)


def _posting_proposals(record: CompanyRecord, site: CareerSite, root: str) -> list[RecheckChange]:
    root_class = classify_url(root)
    site_type = root_class.site_type
    if site_type == CareerSiteType.JOB_POSTING:
        site_type = (
            CareerSiteType.ATS_INSTANCE
            if root_class.ats != AtsKind.UNKNOWN
            else CareerSiteType.COMPANY_CAREER_PORTAL
        )
    changes: list[RecheckChange] = []
    root_site = record.find_site(root)
    if root_site is None or not _already_seen(
        root_site, root_class.ats, site_type, root_class.evidence
    ):
        changes.append(
            RecheckChange(
                company_id=record.id,
                url=site.url,
                action="add_root",
                detail=f"portal root {root}",
                root_url=root,
                ats=root_class.ats,
                site_type=site_type,
                evidence=root_class.evidence,
            )
        )
    changes.append(
        RecheckChange(
            company_id=record.id,
            url=site.url,
            action="reject_posting",
            detail="stored URL is one opening",
        )
    )
    return changes


def _board_proposals(
    record: CompanyRecord,
    site: CareerSite,
    ats: AtsKind,
    evidence: str,
) -> list[RecheckChange]:
    changes: list[RecheckChange] = []
    if REVIEW_NOTE not in (site.notes or ""):
        changes.append(
            RecheckChange(
                company_id=record.id,
                url=site.url,
                action="mark_review",
                detail="job board host; kept for review",
            )
        )
    observed_type = CareerSiteType.JOB_BOARD
    if not _already_seen(site, ats, observed_type, evidence):
        changes.append(
            RecheckChange(
                company_id=record.id,
                url=site.url,
                action="observe",
                detail=f"job board {ats.value}",
                ats=ats,
                site_type=observed_type,
                evidence=evidence,
            )
        )
    return changes


def _ats_proposals(
    record: CompanyRecord,
    site: CareerSite,
    ats: AtsKind,
    site_type: CareerSiteType,
    evidence: str,
) -> list[RecheckChange]:
    if ats == AtsKind.UNKNOWN or ats == site.ats:
        return []
    if site_type == CareerSiteType.JOB_POSTING:
        site_type = CareerSiteType.ATS_INSTANCE
    if _already_seen(site, ats, site_type, evidence):
        return []
    changes = [
        RecheckChange(
            company_id=record.id,
            url=site.url,
            action="observe",
            detail=f"ats {ats.value}; {evidence}",
            ats=ats,
            site_type=site_type,
            evidence=evidence,
        )
    ]
    contradicts = site.ats != AtsKind.UNKNOWN
    if not contradicts and site.status == KnowledgeStatus.CANDIDATE:
        changes.append(
            RecheckChange(
                company_id=record.id,
                url=site.url,
                action="promote",
                detail="technical host evidence",
            )
        )
    return changes


def _already_seen(site: CareerSite, ats: AtsKind, site_type: CareerSiteType, evidence: str) -> bool:
    return any(
        obs.ats == ats and obs.site_type == site_type and obs.evidence == evidence
        for obs in site.observations
    )
