"""SQLAlchemy engine and session helpers."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from sqlalchemy import Date, DateTime, Float, Integer, String, Text, create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.sql.schema import Table

from jobbot.db import models as orm

_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def make_engine(db_path: Path) -> Engine:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    url = f"sqlite:///{db_path}"
    engine = create_engine(url, future=True)
    orm.Base.metadata.create_all(engine)
    _migrate_sqlite(engine)
    return engine


def _sqlite_type(column_type: object) -> str | None:
    """SQLite type for an additive column. Unknown types are skipped, not guessed."""
    if isinstance(column_type, Text):
        return "TEXT"
    if isinstance(column_type, String):
        return f"VARCHAR({column_type.length})" if column_type.length else "VARCHAR(255)"
    if isinstance(column_type, DateTime):
        return "DATETIME"
    if isinstance(column_type, Date):
        return "DATE"
    if isinstance(column_type, Integer):
        return "INTEGER"
    if isinstance(column_type, Float):
        return "FLOAT"
    return None


def _missing_nullable(table: Table, existing: set[str]) -> list[tuple[str, str]]:
    """Nullable columns the ORM has and this file does not. NOT NULL stays put."""
    missing: list[tuple[str, str]] = []
    for column in table.columns:
        name = column.name
        if name in existing or column.primary_key or not column.nullable:
            continue
        if _IDENTIFIER.fullmatch(name) is None or _IDENTIFIER.fullmatch(table.name) is None:
            continue
        col_type = _sqlite_type(column.type)
        if col_type is not None:
            missing.append((name, col_type))
    return missing


def _migrate_sqlite(engine: Engine) -> None:
    """Add nullable columns the ORM gained after create_all (SQLite has no ALTER sync)."""
    with engine.begin() as conn:
        for table in orm.Base.metadata.sorted_tables:
            if _IDENTIFIER.fullmatch(table.name) is None:
                continue
            rows = conn.execute(text(f"PRAGMA table_info({table.name})")).fetchall()
            if not rows:
                continue
            existing = {row[1] for row in rows}
            for name, col_type in _missing_nullable(table, existing):
                conn.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {name} {col_type}"))


def make_readonly_engine(db_path: Path) -> Engine:
    """Open an existing database without creating, migrating or writing it (previews)."""
    uri = f"{db_path.resolve().as_uri()}?mode=ro"
    return create_engine("sqlite://", creator=lambda: sqlite3.connect(uri, uri=True), future=True)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)
