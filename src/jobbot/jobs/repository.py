"""Job persistence repository."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from jobbot.db.models import JobRow
from jobbot.jobs.ids import next_job_id
from jobbot.jobs.parsing import parse_job_text
from jobbot.models.job import JobPosting


class JobRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add_from_text(
        self,
        text: str,
        *,
        source: str = "manual",
        url: str | None = None,
    ) -> JobPosting:
        job_id = next_job_id(self._session)
        job = parse_job_text(text, job_id=job_id, source=source, url=url)
        self.save(job)
        return job

    def save(self, job: JobPosting) -> None:
        row = self._session.get(JobRow, job.id)
        payload = _to_row_fields(job)
        if row is None:
            self._session.add(JobRow(id=job.id, **payload))
        else:
            for key, value in payload.items():
                setattr(row, key, value)
        self._session.commit()

    def find_by_source(self, source: str, source_job_id: str) -> JobPosting | None:
        row = self._session.scalars(
            select(JobRow).where(
                JobRow.source == source,
                JobRow.source_job_id == source_job_id,
            )
        ).first()
        return _from_row(row) if row else None

    def find_by_url(self, url: str) -> JobPosting | None:
        row = self._session.scalars(select(JobRow).where(JobRow.url == url)).first()
        return _from_row(row) if row else None

    def upsert_external(self, job: JobPosting) -> JobPosting:
        """Insert or update by source+source_job_id (or URL). Keeps existing internal id."""
        existing: JobPosting | None = None
        if job.source_job_id:
            existing = self.find_by_source(job.source, job.source_job_id)
        if existing is None and job.url:
            existing = self.find_by_url(job.url)
        if existing is None:
            job.id = next_job_id(self._session)
            self.save(job)
            return job
        job.id = existing.id
        # Preserve note/score unless overwritten
        if job.note is None:
            job.note = existing.note
        if job.match_score is None:
            job.match_score = existing.match_score
        self.save(job)
        return job

    def get(self, job_id: str) -> JobPosting | None:
        row = self._session.get(JobRow, job_id)
        if row is None:
            return None
        return _from_row(row)

    def list_all(self) -> list[JobPosting]:
        rows = self._session.scalars(select(JobRow).order_by(JobRow.id)).all()
        return [_from_row(r) for r in rows]

    def update_match_score(self, job_id: str, score: float) -> None:
        row = self._session.get(JobRow, job_id)
        if row is None:
            msg = f"Job not found: {job_id}"
            raise KeyError(msg)
        row.match_score = score
        self._session.commit()

    def set_note(self, job_id: str, note: str) -> None:
        row = self._session.get(JobRow, job_id)
        if row is None:
            msg = f"Job not found: {job_id}"
            raise KeyError(msg)
        row.note = note
        self._session.commit()


class StoredJobIndex:
    """Which jobs are already stored, read without touching the database file.

    A preview (`--dry-run`) must not create the database or migrate it, so this
    opens SQLite read-only and asks for three columns every version has.
    """

    def __init__(self, rows: list[tuple[str, str, str | None, str | None]] | None = None) -> None:
        self._by_source: dict[tuple[str, str], str] = {}
        self._by_url: dict[str, str] = {}
        for job_id, source, source_job_id, url in rows or []:
            if source_job_id:
                self._by_source.setdefault((source, source_job_id), job_id)
            if url:
                self._by_url.setdefault(url, job_id)

    @classmethod
    def read_only(cls, db_path: Path) -> StoredJobIndex:
        if not db_path.is_file():
            return cls()
        uri = f"{db_path.resolve().as_uri()}?mode=ro"
        try:
            with closing(sqlite3.connect(uri, uri=True)) as conn:
                rows = conn.execute("SELECT id, source, source_job_id, url FROM jobs").fetchall()
        except sqlite3.Error:
            return cls()
        return cls([(str(r[0]), str(r[1]), r[2], r[3]) for r in rows])

    @classmethod
    def from_repository(cls, repo: JobRepository) -> StoredJobIndex:
        return cls([(j.id, j.source, j.source_job_id, j.url) for j in repo.list_all()])

    def lookup(self, job: JobPosting) -> str | None:
        if job.source_job_id:
            found = self._by_source.get((job.source, job.source_job_id))
            if found:
                return found
        return self._by_url.get(job.url) if job.url else None


def write_job_json(job: JobPosting, output_dir: Path) -> Path:
    job_dir = output_dir / "jobs" / job.id
    job_dir.mkdir(parents=True, exist_ok=True)
    path = job_dir / "job.json"
    path.write_text(job.model_dump_json(indent=2), encoding="utf-8")
    return path


def _to_row_fields(job: JobPosting) -> dict[str, object]:
    return {
        "source": job.source,
        "source_job_id": job.source_job_id,
        "url": job.url,
        "title": job.title,
        "company": job.company,
        "location": job.location,
        "description": job.description,
        "raw_description": job.raw_description,
        "requirements_json": json.dumps(job.requirements, ensure_ascii=False),
        "skills_json": json.dumps(job.skills, ensure_ascii=False),
        "seniority": job.seniority,
        "language_requirements_json": json.dumps(job.language_requirements, ensure_ascii=False),
        "employment_type": job.employment_type,
        "remote_type": job.remote_type,
        "ats_url": job.ats_url,
        "ats_kind": job.ats_kind,
        "posted_at": job.posted_at,
        "discovered_at": job.discovered_at
        if isinstance(job.discovered_at, datetime)
        else job.discovered_at,
        "note": job.note,
        "match_score": job.match_score,
        "closes_at": job.closes_at.isoformat() if job.closes_at else None,
        "closes_on": job.closes_on,
        "closes_text": job.closes_text,
        "ats_signals_json": json.dumps(job.ats_signals) if job.ats_signals else None,
    }


def _closes_at(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _as_utc(moment: datetime | None) -> datetime | None:
    """SQLite drops tzinfo; everything we store is UTC."""
    if moment is None or moment.tzinfo is not None:
        return moment
    return moment.replace(tzinfo=UTC)


def _from_row(row: JobRow) -> JobPosting:
    return JobPosting(
        id=row.id,
        source=row.source,
        source_job_id=row.source_job_id,
        url=row.url,
        title=row.title,
        company=row.company,
        location=row.location,
        description=row.description,
        raw_description=row.raw_description,
        requirements=json.loads(row.requirements_json or "[]"),
        skills=json.loads(row.skills_json or "[]"),
        seniority=row.seniority,
        language_requirements=json.loads(row.language_requirements_json or "[]"),
        employment_type=row.employment_type,
        remote_type=row.remote_type,
        ats_url=getattr(row, "ats_url", None),
        ats_kind=getattr(row, "ats_kind", None),
        posted_at=_as_utc(getattr(row, "posted_at", None)),
        discovered_at=row.discovered_at,
        note=row.note,
        match_score=row.match_score,
        closes_at=_closes_at(getattr(row, "closes_at", None)),
        closes_on=getattr(row, "closes_on", None),
        closes_text=getattr(row, "closes_text", None),
        ats_signals=json.loads(getattr(row, "ats_signals_json", None) or "{}"),
    )
