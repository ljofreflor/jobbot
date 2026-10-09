"""SQLAlchemy engine and session helpers."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from jobbot.db import models as orm

_JOB_EXTRA_COLUMNS: dict[str, str] = {
    "ats_url": "TEXT",
    "ats_kind": "VARCHAR(64)",
    "posted_at": "DATETIME",
    "closes_at": "TEXT",
    "closes_on": "DATE",
    "closes_text": "TEXT",
    "ats_signals_json": "TEXT",
    "open_status": "VARCHAR(16)",
    "checked_at": "DATETIME",
    "open_evidence": "TEXT",
}


def make_engine(db_path: Path) -> Engine:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    url = f"sqlite:///{db_path}"
    engine = create_engine(url, future=True)
    orm.Base.metadata.create_all(engine)
    _migrate_sqlite(engine)
    return engine


def _migrate_sqlite(engine: Engine) -> None:
    """Add columns introduced after first create_all (SQLite has no ALTER sync)."""
    with engine.begin() as conn:
        rows = conn.execute(text("PRAGMA table_info(jobs)")).fetchall()
        existing = {r[1] for r in rows}
        for name, col_type in _JOB_EXTRA_COLUMNS.items():
            if name not in existing:
                conn.execute(text(f"ALTER TABLE jobs ADD COLUMN {name} {col_type}"))


def make_readonly_engine(db_path: Path) -> Engine:
    """Open an existing database without creating, migrating or writing it (previews)."""
    uri = f"{db_path.resolve().as_uri()}?mode=ro"
    return create_engine("sqlite://", creator=lambda: sqlite3.connect(uri, uri=True), future=True)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)
