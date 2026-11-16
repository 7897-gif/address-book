"""SQLite helpers for the address book.

The whole application talks to SQLite through this module so that the schema
lives in exactly one place.
"""

from __future__ import annotations

import datetime as _dt
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS contacts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT    NOT NULL,
    company    TEXT    NOT NULL DEFAULT '',
    title      TEXT    NOT NULL DEFAULT '',
    notes      TEXT    NOT NULL DEFAULT '',
    favorite   INTEGER NOT NULL DEFAULT 0,
    created_at TEXT    NOT NULL,
    updated_at TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS contact_methods (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    contact_id INTEGER NOT NULL REFERENCES contacts (id) ON DELETE CASCADE,
    kind       TEXT    NOT NULL,
    label      TEXT    NOT NULL DEFAULT '',
    value      TEXT    NOT NULL,
    position   INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_methods_contact ON contact_methods (contact_id);
"""


def now() -> str:
    """Timestamp used for created_at / updated_at."""
    return _dt.datetime.now().replace(microsecond=0).isoformat(sep=" ")


def connect(db_path: str | Path) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path: str | Path) -> None:
    with connect(db_path) as conn:
        conn.executescript(SCHEMA)
