"""Import a researched employer↔channel inventory into the companies registry (#269).

The chile tip shipped a parallel ``SourceCatalog``. Policy keeps one model: channels
become ``CareerSite`` rows (always ``candidate``). Declared counts must match or
nothing is written.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import BaseModel, Field

from jobbot.companies.models import CareerSiteType, DiscoverySource, KnowledgeStatus
from jobbot.companies.oneshot import CompanyPortalCandidate
from jobbot.companies.registry import CompanyRegistry, ObserveOutcome
from jobbot.companies.urls import (
    PrivateRouteRejected,
    ensure_not_reserved,
    semantic_key,
    slugify,
)
from jobbot.portals.detect import AtsKind


class SeedSourceType(StrEnum):
    LISTING = "listing"
    ACCESS = "access"
    CV_INBOX = "cv_inbox"
    JOB_POSTING = "job_posting"
    UNKNOWN = "unknown"


class SeedReadState(StrEnum):
    NOT_READ = "not_read"
    FETCHED = "fetched"
    JS_REQUIRED = "js_required"
    NO_CONTENT = "no_content"
    READER_ERROR = "reader_error"
    PENDING_DESTINATION = "pending_destination"


class SeedChannel(BaseModel):
    employer: str = Field(min_length=1)
    url: str = Field(min_length=1)
    sector: str | None = None
    source: str | None = None
    type: SeedSourceType = SeedSourceType.UNKNOWN
    ats: str = "unknown"
    read: SeedReadState = SeedReadState.NOT_READ
    notes: str | None = None
    enabled: bool = False


class SeedExpectations(BaseModel):
    employers: int | None = None
    channels: int | None = None
    sectors: int | None = None
    by_type: dict[str, int] = Field(default_factory=dict)
    by_read: dict[str, int] = Field(default_factory=dict)


class SeedDocument(BaseModel):
    catalog_version: str = "0.1.0"
    country: str | None = None
    researched_at: date | None = None
    notes: str | None = None
    expected: SeedExpectations = Field(default_factory=SeedExpectations)
    channels: list[SeedChannel] = Field(default_factory=list)
    research_queue: dict[str, list[str]] = Field(default_factory=dict)


class IssueLevel(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass(frozen=True)
class ImportIssue:
    level: IssueLevel
    subject: str
    reason: str


@dataclass(frozen=True)
class CatalogImportReport:
    employers: int = 0
    channels: int = 0
    sectors: int = 0
    by_type: Mapping[str, int] = field(default_factory=dict)
    by_read: Mapping[str, int] = field(default_factory=dict)
    expected: SeedExpectations = field(default_factory=SeedExpectations)
    issues: tuple[ImportIssue, ...] = ()
    rejected: int = 0
    outcomes: tuple[ObserveOutcome, ...] = ()

    @property
    def errors(self) -> tuple[ImportIssue, ...]:
        return tuple(i for i in self.issues if i.level is IssueLevel.ERROR)

    @property
    def ok(self) -> bool:
        return not self.errors


def load_catalog_seed(path: Path) -> SeedDocument:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        msg = f"{path} must be a mapping with channels:"
        raise ValueError(msg)
    return SeedDocument.model_validate(raw)


def _ats_of(raw: str) -> AtsKind:
    folded = (raw or "unknown").strip().casefold()
    try:
        return AtsKind(folded)
    except ValueError:
        return AtsKind.UNKNOWN


def _site_type_of(kind: SeedSourceType) -> CareerSiteType:
    if kind is SeedSourceType.JOB_POSTING:
        return CareerSiteType.JOB_POSTING
    if kind is SeedSourceType.LISTING:
        return CareerSiteType.ATS_INSTANCE
    if kind is SeedSourceType.ACCESS:
        return CareerSiteType.COMPANY_CAREER_PORTAL
    return CareerSiteType.UNKNOWN


def _evidence(channel: SeedChannel, researched_at: date | None) -> str:
    bits = [f"catalog seed read={channel.read.value}"]
    if researched_at is not None:
        bits.append(f"researched_at={researched_at.isoformat()}")
    if channel.notes:
        bits.append(channel.notes.strip())
    return "; ".join(bits)


def candidates_from_seed(
    doc: SeedDocument,
) -> tuple[list[CompanyPortalCandidate], CatalogImportReport]:
    """Turn seed rows into candidates. Refusals are reported, never dropped silently."""
    issues: list[ImportIssue] = []
    candidates: list[CompanyPortalCandidate] = []
    seen_keys: dict[str, str] = {}
    by_type: Counter[str] = Counter()
    by_read: Counter[str] = Counter()
    employers: set[str] = set()
    sectors: set[str] = set()
    rejected = 0
    researched = (
        datetime(doc.researched_at.year, doc.researched_at.month, doc.researched_at.day, tzinfo=UTC)
        if doc.researched_at
        else None
    )

    for channel in doc.channels:
        by_type[channel.type.value] += 1
        by_read[channel.read.value] += 1
        employers.add(channel.employer.casefold())
        if channel.sector:
            sectors.add(channel.sector)
        if channel.enabled:
            issues.append(
                ImportIssue(
                    IssueLevel.ERROR,
                    channel.employer,
                    "seed channel is enabled; catalog import never activates",
                )
            )
            rejected += 1
            continue
        try:
            url = ensure_not_reserved(channel.url)
        except PrivateRouteRejected as exc:
            issues.append(ImportIssue(IssueLevel.ERROR, channel.url, str(exc)))
            rejected += 1
            continue
        key = semantic_key(url)
        prior = seen_keys.get(key)
        if prior is not None and prior != channel.employer.casefold():
            issues.append(
                ImportIssue(
                    IssueLevel.WARNING,
                    url,
                    f"same public key already claimed by {prior!r}; shared channel kept once",
                )
            )
        if key in seen_keys:
            continue
        seen_keys[key] = channel.employer.casefold()
        candidates.append(
            CompanyPortalCandidate(
                company=channel.employer,
                company_id=slugify(channel.employer),
                country=doc.country,
                sector=channel.sector,
                career_url=url,
                site_type=_site_type_of(channel.type),
                ats=_ats_of(channel.ats),
                reached_from=channel.source,
                evidence=_evidence(channel, doc.researched_at),
                source=DiscoverySource.USER_OBSERVATION,
                checked_at=researched or datetime.now(UTC),
                status=KnowledgeStatus.CANDIDATE,
            )
        )

    report = _counts_report(
        employers=len(employers),
        channels=len(doc.channels),
        sectors=len(sectors),
        by_type=dict(by_type),
        by_read=dict(by_read),
        expected=doc.expected,
        issues=tuple(issues),
        rejected=rejected,
    )
    return candidates, report


def _counts_report(
    *,
    employers: int,
    channels: int,
    sectors: int,
    by_type: dict[str, int],
    by_read: dict[str, int],
    expected: SeedExpectations,
    issues: tuple[ImportIssue, ...],
    rejected: int,
    outcomes: tuple[ObserveOutcome, ...] = (),
) -> CatalogImportReport:
    extra: list[ImportIssue] = list(issues)
    pairs: list[tuple[str, int | None, int]] = [
        ("employers", expected.employers, employers),
        ("channels", expected.channels, channels),
        ("sectors", expected.sectors, sectors),
    ]
    for label, want, got in pairs:
        if want is not None and want != got:
            extra.append(
                ImportIssue(
                    IssueLevel.ERROR,
                    label,
                    f"expected {want}, read {got}",
                )
            )
    for label, want in expected.by_type.items():
        got = by_type.get(label, 0)
        if want != got:
            extra.append(
                ImportIssue(IssueLevel.ERROR, f"by_type.{label}", f"expected {want}, read {got}")
            )
    for label, want in expected.by_read.items():
        got = by_read.get(label, 0)
        if want != got:
            extra.append(
                ImportIssue(IssueLevel.ERROR, f"by_read.{label}", f"expected {want}, read {got}")
            )
    return CatalogImportReport(
        employers=employers,
        channels=channels,
        sectors=sectors,
        by_type=by_type,
        by_read=by_read,
        expected=expected,
        issues=tuple(extra),
        rejected=rejected,
        outcomes=outcomes,
    )


def import_catalog_seed(
    registry: CompanyRegistry,
    doc: SeedDocument,
    *,
    apply: bool,
) -> CatalogImportReport:
    """Dry-run by default. ``apply`` writes only when declared counts match."""
    candidates, report = candidates_from_seed(doc)
    if not report.ok or not apply:
        return report
    from jobbot.companies.oneshot import import_candidates

    outcomes = import_candidates(registry, candidates)
    return CatalogImportReport(
        employers=report.employers,
        channels=report.channels,
        sectors=report.sectors,
        by_type=report.by_type,
        by_read=report.by_read,
        expected=report.expected,
        issues=report.issues,
        rejected=report.rejected,
        outcomes=tuple(outcomes),
    )


def render_catalog_import_report(report: CatalogImportReport, *, applied: bool) -> list[str]:
    lines = [
        f"employers={report.employers} channels={report.channels} sectors={report.sectors}",
        f"by_type={dict(report.by_type)}",
        f"by_read={dict(report.by_read)}",
    ]
    if report.rejected:
        lines.append(f"rejected={report.rejected}")
    for issue in report.issues:
        lines.append(f"{issue.level.value}: {issue.subject}: {issue.reason}")
    if applied and report.ok:
        created = sum(1 for o in report.outcomes if o.created_site)
        merged = sum(1 for o in report.outcomes if o.merged)
        lines.append(f"applied: created_sites={created} merged={merged}")
    elif report.ok:
        lines.append("dry-run: counts match; pass --apply to write candidates into companies")
    else:
        lines.append("nothing written: fix the seed or the expected counts first")
    return lines
