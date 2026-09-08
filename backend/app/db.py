"""SQLite persistence.

Uses the standard-library sqlite3 driver directly behind a small repository
layer instead of an ORM. Two reasons: the project then installs and runs with no
database dependency at all, and every data-access path stays unit-testable
without booting the web framework.
"""
from __future__ import annotations

import contextlib
import os
import sqlite3

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    email          TEXT NOT NULL UNIQUE,
    name           TEXT NOT NULL DEFAULT '',
    password_hash  TEXT NOT NULL,
    household_size INTEGER NOT NULL DEFAULT 3,
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pantry_items (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    food_id        TEXT NOT NULL,
    display_name   TEXT NOT NULL,
    category       TEXT NOT NULL,
    grams_initial  REAL NOT NULL,
    grams_remaining REAL NOT NULL,
    storage        TEXT NOT NULL,
    container      TEXT NOT NULL DEFAULT 'default',
    is_covered     INTEGER NOT NULL DEFAULT 1,
    opened         INTEGER NOT NULL DEFAULT 0,
    purchase_date  TEXT NOT NULL,
    expiry_date    TEXT NOT NULL,
    status         TEXT NOT NULL DEFAULT 'active',
    notes          TEXT NOT NULL DEFAULT '',
    created_at     TEXT NOT NULL,
    resolved_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_items_user_status ON pantry_items(user_id, status);
CREATE INDEX IF NOT EXISTS idx_items_user_expiry ON pantry_items(user_id, expiry_date);

CREATE TABLE IF NOT EXISTS events (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    item_id         INTEGER,
    food_id         TEXT NOT NULL DEFAULT '',
    category        TEXT NOT NULL DEFAULT '',
    event_type      TEXT NOT NULL,
    grams           REAL NOT NULL DEFAULT 0,
    waste_reason    TEXT NOT NULL DEFAULT '',
    co2e_kg         REAL NOT NULL DEFAULT 0,
    water_l         REAL NOT NULL DEFAULT 0,
    value_inr       REAL NOT NULL DEFAULT 0,
    risk_at_resolve REAL,
    occurred_at     TEXT NOT NULL,
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_user_time ON events(user_id, occurred_at);
CREATE INDEX IF NOT EXISTS idx_events_user_type ON events(user_id, event_type);
"""


def connect(path: str | None = None) -> sqlite3.Connection:
    target = path or DB_PATH
    if target != ":memory:":
        directory = os.path.dirname(os.path.abspath(target))
        if directory:
            os.makedirs(directory, exist_ok=True)
    conn = sqlite3.connect(target, timeout=15.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    # Safe lightweight schema migrations for existing SQLite databases
    try:
        conn.execute("ALTER TABLE pantry_items ADD COLUMN container TEXT NOT NULL DEFAULT 'default'")
    except sqlite3.OperationalError:
        pass
    try:
        conn.execute("ALTER TABLE pantry_items ADD COLUMN is_covered INTEGER NOT NULL DEFAULT 1")
    except sqlite3.OperationalError:
        pass
    return conn


@contextlib.contextmanager
def session(path: str | None = None):
    """Transactional scope. Commits on success, rolls back on any exception."""
    conn = connect(path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(path: str | None = None) -> None:
    with session(path) as conn:
        conn.executescript(SCHEMA)


def reset_db(path: str | None = None) -> None:
    """Drops and recreates everything. Used by tests and the demo seeder."""
    with session(path) as conn:
        for t in ("events", "pantry_items", "users"):
            conn.execute("DROP TABLE IF EXISTS %s" % t)
        conn.executescript(SCHEMA)
