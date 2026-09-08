from __future__ import annotations

import datetime as dt
import sqlite3


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def create(conn: sqlite3.Connection, email: str, name: str, password_hash: str,
           household_size: int = 3) -> int:
    cur = conn.execute(
        "INSERT INTO users (email, name, password_hash, household_size, created_at)"
        " VALUES (?,?,?,?,?)",
        (email.strip().lower(), name.strip(), password_hash, int(household_size), _now()),
    )
    return int(cur.lastrowid)


def by_email(conn: sqlite3.Connection, email: str) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM users WHERE email = ?", (email.strip().lower(),)
    ).fetchone()


def by_id(conn: sqlite3.Connection, user_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()


def update_profile(conn: sqlite3.Connection, user_id: int, name: str | None = None,
                   household_size: int | None = None) -> None:
    sets, args = [], []
    if name is not None:
        sets.append("name = ?")
        args.append(name.strip())
    if household_size is not None:
        sets.append("household_size = ?")
        args.append(max(1, int(household_size)))
    if not sets:
        return
    args.append(user_id)
    conn.execute("UPDATE users SET %s WHERE id = ?" % ", ".join(sets), args)


def count(conn: sqlite3.Connection) -> int:
    return int(conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"])


def delete(conn: sqlite3.Connection, user_id: int) -> bool:
    """Removes the account and, by ON DELETE CASCADE, its items and events.

    The cascade only fires because connect() turns foreign keys on - SQLite
    ignores them by default, which would quietly orphan every row instead.
    """
    cur = conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    return cur.rowcount > 0
