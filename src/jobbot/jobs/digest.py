"""A shareable daily summary of new, still-open postings. Nothing is sent."""

from __future__ import annotations

import json
import tomllib
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import yaml

from jobbot.config import JobbotConfig
from jobbot.jobs.conditions import ConditionKind, posting_conditions
from jobbot.jobs.open_signals import OpenStatus
from jobbot.models.candidate import Candidate
from jobbot.models.job import JobPosting
from jobbot.ops.pii_guard import scan_text

WHATSAPP_LIMIT = 4096
SALARY_MISSING = "renta no publicada"
CLOSING_MISSING = "cierre no informado"
_TRACKING = {"fbclid", "gclid", "mc_eid", "rcm"}
_ELIGIBILITY = {"admisible", "no_admisible", "dudoso"}
_CHILE = {"cl", "chile"}


class DigestError(ValueError):
    """The digest cannot be built from the arguments or the workspace."""


@dataclass(frozen=True)
class DigestEntry:
    job_id: str
    title: str
    company: str
    salary: str
    closing: str
    url: str
    why: str | None = None
    doubtful: bool = False


def resolve_timezone(config: JobbotConfig, country: str | None) -> ZoneInfo:
    """Workspace zone, or Santiago when the candidate's country is Chile."""
    name = _configured_timezone(config.root)
    if name is None and (country or "").strip().casefold() in _CHILE:
        name = "America/Santiago"
    if name is None:
        raise DigestError("sin zona horaria: configura [workspace] timezone")
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise DigestError(f"zona horaria desconocida: {name}") from exc


def parse_since(text: str | None, *, now: datetime, zone: ZoneInfo, state_path: Path) -> datetime:
    """``--since``, else the last digest, else 24 hours before ``now``."""
    if text:
        raw = text.strip()
        if len(raw) == 10:
            try:
                day = datetime.strptime(raw, "%Y-%m-%d")
            except ValueError as exc:
                raise DigestError(f"--since inválido: {text}") from exc
            return day.replace(tzinfo=zone)
        try:
            parsed = datetime.fromisoformat(raw)
        except ValueError as exc:
            raise DigestError(f"--since inválido: {text}") from exc
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=zone)
        return parsed.astimezone(UTC)
    saved = load_last_digest(state_path)
    if saved is not None:
        return saved
    return now - timedelta(hours=24)


def load_last_digest(path: Path) -> datetime | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    raw = data.get("last_digest") if isinstance(data, dict) else None
    if not isinstance(raw, str):
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def save_last_digest(path: Path, moment: datetime) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"last_digest": moment.astimezone(UTC).isoformat()}
    path.write_text(json.dumps(payload) + "\n", encoding="utf-8")


def load_eligibility(path: Path) -> dict[str, str]:
    """Job id → admisible | no_admisible | dudoso. Missing file means no marks."""
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise DigestError("data/eligibility.yaml debe ser un mapa de id a marca")
    marks: dict[str, str] = {}
    for key, value in data.items():
        mark = str(value).strip().casefold()
        if mark not in _ELIGIBILITY:
            raise DigestError(f"marca de admisibilidad desconocida para {key}: {value}")
        marks[str(key)] = mark
    return marks


def select_entries(
    jobs: list[JobPosting],
    *,
    since: datetime,
    zone: ZoneInfo,
    eligibility: dict[str, str],
    reasons: dict[str, str],
    include_doubtful: bool,
    limit: int,
) -> list[DigestEntry]:
    chosen: list[JobPosting] = []
    for job in jobs:
        if job.invalid_reason or job.open_status == OpenStatus.CLOSED:
            continue
        mark = eligibility.get(job.id)
        if mark == "no_admisible":
            continue
        if mark == "dudoso" and not include_doubtful:
            continue
        if _activity(job) <= since.astimezone(UTC):
            continue
        chosen.append(job)
    chosen.sort(key=_closing_sort)
    return [
        DigestEntry(
            job_id=job.id,
            title=job.title,
            company=job.company,
            salary=_salary(job),
            closing=_closing(job, zone),
            url=public_url(job.url or ""),
            why=reasons.get(job.id) or None,
            doubtful=eligibility.get(job.id) == "dudoso",
        )
        for job in chosen[: max(limit, 0)]
    ]


def render_whatsapp(entries: list[DigestEntry], *, since: datetime) -> list[str]:
    if not entries:
        return [empty_line(since)]
    blocks = [_whatsapp_block(entry) for entry in entries]
    return _pack(blocks)


def render_markdown(entries: list[DigestEntry], *, since: datetime) -> str:
    if not entries:
        return empty_line(since) + "\n"
    lines = []
    for entry in entries:
        link = f"[{entry.title}]({entry.url})" if entry.url else entry.title
        lines.append(f"- {link} — {entry.company}")
        lines.append(f"  - {entry.salary}")
        lines.append(f"  - {entry.closing}")
        if entry.why:
            lines.append(f"  - {entry.why}")
        if entry.doubtful:
            lines.append("  - dudoso")
    return "\n".join(lines) + "\n"


def empty_line(since: datetime) -> str:
    return f"sin oportunidades nuevas desde {since.date().isoformat()}"


def public_url(url: str) -> str:
    """Drop tracking parameters. The rest of the query stays."""
    if not url:
        return ""
    parts = urlsplit(url)
    kept = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in _TRACKING
    ]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(kept), ""))


def refuse_pii(text: str) -> None:
    findings = scan_text(text, "digest")
    if not findings:
        return
    kinds = ", ".join(sorted({item.reason for item in findings}))
    raise DigestError(f"la salida tiene datos de contacto ({kinds})")


def output_path(config: JobbotConfig, raw: str) -> Path:
    path = Path(raw)
    if not path.is_absolute():
        path = config.root / path
    resolved = path.resolve()
    output = config.output_dir.resolve()
    if resolved != output and output not in resolved.parents:
        raise DigestError("--out tiene que quedar bajo output/")
    return resolved


def _whatsapp_block(entry: DigestEntry) -> str:
    lines = [
        f"*{entry.title}*",
        entry.company,
        entry.salary,
        entry.closing,
    ]
    if entry.url:
        lines.append(entry.url)
    if entry.why:
        lines.append(entry.why)
    if entry.doubtful:
        lines.append("dudoso")
    return "\n".join(lines)


def _pack(blocks: list[str], *, limit: int = WHATSAPP_LIMIT) -> list[str]:
    prefix = len("(99/99)\n")
    budget = limit - prefix
    chunks: list[str] = []
    current = ""
    for block in blocks:
        if len(block) > budget:
            block = block[:budget]
        piece = block if not current else f"{current}\n\n{block}"
        if len(piece) <= budget:
            current = piece
            continue
        if current:
            chunks.append(current)
        current = block
    if current:
        chunks.append(current)
    if len(chunks) <= 1:
        return chunks
    total = len(chunks)
    return [f"({index}/{total})\n{body}" for index, body in enumerate(chunks, start=1)]


def _salary(job: JobPosting) -> str:
    for condition in posting_conditions(job):
        if condition.kind == ConditionKind.SALARY and condition.shown and condition.detail:
            return condition.detail
    return SALARY_MISSING


def _closing(job: JobPosting, zone: ZoneInfo) -> str:
    if job.closes_at is None:
        if job.closes_on is not None:
            return f"{job.closes_on.isoformat()} (hora no publicada)"
        return CLOSING_MISSING
    moment = job.closes_at if job.closes_at.tzinfo else job.closes_at.replace(tzinfo=UTC)
    local = moment.astimezone(zone)
    local_name = "Chile" if getattr(zone, "key", "") == "America/Santiago" else str(zone)
    original = getattr(moment.tzinfo, "key", None) or str(moment.tzinfo)
    return (
        f"{local.strftime('%d-%m %H:%M')} ({local_name}) — "
        f"{moment.strftime('%d-%m %H:%M')} ({original})"
    )


def _activity(job: JobPosting) -> datetime:
    moments = [_aware(job.discovered_at)]
    if job.checked_at is not None:
        moments.append(_aware(job.checked_at))
    return max(moments)


def _aware(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment.astimezone(UTC)


def _closing_sort(job: JobPosting) -> tuple[int, datetime]:
    if job.closes_at is not None:
        return (0, _aware(job.closes_at))
    if job.closes_on is not None:
        return (1, datetime.combine(job.closes_on, datetime.min.time(), tzinfo=UTC))
    return (2, datetime(9999, 12, 31, tzinfo=UTC))


def _configured_timezone(root: Path) -> str | None:
    path = root / ".jobbot.toml"
    if not path.is_file():
        return None
    with path.open("rb") as handle:
        raw = tomllib.load(handle)
    section = raw.get("workspace")
    if not isinstance(section, dict):
        return None
    name = section.get("timezone")
    if isinstance(name, str) and name.strip():
        return name.strip()
    return None


def why_line(candidate: Candidate, job: JobPosting) -> str | None:
    """Up to two matcher reasons. Omitted when the matcher has nothing to say."""
    from jobbot.matching.analyzer import RuleBasedJobAnalyzer
    from jobbot.matching.scoring import match_reasons

    reasons = match_reasons(RuleBasedJobAnalyzer().analyze(candidate, job), limit=2)
    text = "; ".join(reasons).strip()
    return text or None
