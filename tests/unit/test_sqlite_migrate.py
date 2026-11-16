"""Additive SQLite migration follows the ORM. It does not rewrite what is already there."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from sqlalchemy import text

from jobbot.db.engine import make_engine


def _types(db_path: Path, table: str) -> dict[str, str]:
    engine = make_engine(db_path)
    with engine.begin() as conn:
        rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
    engine.dispose()
    return {row[1]: row[2] for row in rows}


def test_nullable_column_is_added_on_a_table_other_than_jobs(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE applications (id VARCHAR(32) PRIMARY KEY)")
    types = _types(db_path, "applications")
    assert types["package_dir"] == "TEXT"


def test_existing_column_type_is_kept_and_not_null_is_not_added(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.sqlite"
    with sqlite3.connect(db_path) as conn:
        conn.execute("CREATE TABLE jobs (id VARCHAR(32) PRIMARY KEY, posted_at INTEGER)")
    types = _types(db_path, "jobs")
    assert types["posted_at"] == "INTEGER"
    assert types["ats_url"] == "TEXT"
    assert types["ats_kind"] == "VARCHAR(64)"
    assert types["closes_on"] == "DATE"
    assert types["checked_at"] == "DATETIME"
    assert "title" not in types
