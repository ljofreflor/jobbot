"""`jobs discover`: one command, one adapter per public source, a preview before storing.

Each source registers a factory here (Workday first; UN Careers, Greenhouse … later).
An adapter turns one site into a `SiteOutcome`; this module decides, per posting, what
storing would do — so `--dry-run` and the real run print the same table. A site that
fails is reported and the others continue (#176).
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from jobbot.companies.models import KnowledgeStatus
from jobbot.companies.registry import CompanyRegistry
from jobbot.exit_codes import GENERIC_FAILURE, SUCCESS, UI_CHANGED
from jobbot.jobs.closing import ClosingState, closing_state
from jobbot.jobs.repository import StoredJobIndex
from jobbot.models.job import JobPosting


class SiteStatus(StrEnum):
    OK = "ok"
    EMPTY = "sin resultados"
    FAILED = "falló"
    ROBOTS = "bloqueado: robots"
    CHANGED = "forma cambiada"


@dataclass
class SiteOutcome:
    site: str
    status: SiteStatus
    jobs: list[JobPosting] = field(default_factory=list)
    detail: str = ""
    total: int | None = None

    @property
    def answered(self) -> bool:
        return self.status in {SiteStatus.OK, SiteStatus.EMPTY}


@dataclass(frozen=True)
class SiteTarget:
    url: str
    company: str | None = None


class DiscoverAdapter(Protocol):
    name: str

    def site_target(self, raw: str) -> SiteTarget:
        """Validate one ``--site`` value; ``ValueError`` with a clear message if not this source."""
        ...

    def registry_targets(self, registry: CompanyRegistry) -> list[SiteTarget]: ...

    def discover_site(
        self,
        target: SiteTarget,
        *,
        query: str,
        limit: int,
        details: bool,
    ) -> SiteOutcome: ...


_FACTORIES: dict[str, Callable[[], DiscoverAdapter]] = {}


def register_source(name: str, factory: Callable[[], DiscoverAdapter]) -> None:
    _FACTORIES[name] = factory


def source_names() -> list[str]:
    _load_builtin()
    return sorted(_FACTORIES)


def discover_adapter(name: str) -> DiscoverAdapter:
    _load_builtin()
    factory = _FACTORIES.get(name)
    if factory is None:
        known = ", ".join(sorted(_FACTORIES)) or "none"
        msg = f"Unknown --source {name!r} (known: {known})"
        raise ValueError(msg)
    return factory()


def _load_builtin() -> None:
    if "workday" not in _FACTORIES:
        from jobbot.adapters.workday.jobs import WorkdayDiscover

        register_source("workday", WorkdayDiscover)


def registry_sites_for(registry: CompanyRegistry, ats: str) -> list[SiteTarget]:
    """Career sites of one ATS that were not rejected, named after their company."""
    out: list[SiteTarget] = []
    for record in registry.companies:
        for site in record.career_sites:
            if str(site.ats) == ats and site.status != KnowledgeStatus.REJECTED:
                out.append(SiteTarget(url=site.url, company=record.name))
    return out


class Action(StrEnum):
    STORE = "guardar"
    UPDATE = "actualizar"
    SKIP = "omitir"


@dataclass(frozen=True)
class Decision:
    job: JobPosting
    action: Action
    reason: str = ""
    existing_id: str | None = None
    closing: ClosingState | None = None

    @property
    def stores(self) -> bool:
        return self.action is not Action.SKIP

    @property
    def label(self) -> str:
        bits = [self.action.value]
        if self.existing_id:
            bits.append(self.existing_id)
        if self.reason:
            bits.append(f"({self.reason})")
        if self.closing is ClosingState.SOON:
            bits.append("· cierra pronto")
        return " ".join(bits)


def unique_jobs(jobs: Sequence[JobPosting]) -> list[JobPosting]:
    """Several queries and sites can surface one vacancy; keep its first sighting."""
    seen: set[tuple[str, ...]] = set()
    out: list[JobPosting] = []
    for job in jobs:
        key = (job.source, job.source_job_id) if job.source_job_id else (job.url or job.title,)
        if key not in seen:
            seen.add(key)
            out.append(job)
    return out


def decide(
    jobs: Sequence[JobPosting],
    index: StoredJobIndex,
    *,
    now: datetime,
) -> list[Decision]:
    decisions: list[Decision] = []
    for job in unique_jobs(jobs):
        state = closing_state(job.closes_at, job.closes_on, now=now)
        existing = index.lookup(job)
        if state is ClosingState.EXPIRED:
            decisions.append(Decision(job, Action.SKIP, "cierre vencido", existing, state))
        elif job.ats_signals.get("can_apply") is False:
            decisions.append(Decision(job, Action.SKIP, "no admite postulación", existing, state))
        elif existing:
            decisions.append(Decision(job, Action.UPDATE, "", existing, state))
        else:
            decisions.append(Decision(job, Action.STORE, "", None, state))
    return decisions


def exit_code_for(outcomes: Sequence[SiteOutcome]) -> int:
    """0 if any site answered; 5 if the only site changed shape; else 1."""
    if any(outcome.answered for outcome in outcomes):
        return SUCCESS
    if len(outcomes) == 1 and outcomes[0].status is SiteStatus.CHANGED:
        return UI_CHANGED
    return GENERIC_FAILURE
