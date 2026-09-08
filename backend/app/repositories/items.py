from __future__ import annotations

import datetime as dt
import sqlite3

ACTIVE = "active"
RESOLVED = ("consumed", "wasted", "donated")

FIELDS = (
    "food_id", "display_name", "category", "grams_initial", "grams_remaining",
    "storage", "container", "is_covered", "opened", "purchase_date", "expiry_date", "status", "notes",
)


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def create(conn: sqlite3.Connection, user_id: int, **kw) -> int:
    row = {
        "food_id": kw["food_id"],
        "display_name": kw.get("display_name") or kw["food_id"],
        "category": kw.get("category", ""),
        "grams_initial": float(kw["grams_initial"]),
        "grams_remaining": float(kw.get("grams_remaining", kw["grams_initial"])),
        "storage": kw.get("storage", "fridge"),
        "container": str(kw.get("container") or "default").lower(),
        "is_covered": 0 if kw.get("is_covered") is False else 1,
        "opened": 1 if kw.get("opened") else 0,
        "purchase_date": kw["purchase_date"],
        "expiry_date": kw["expiry_date"],
        "status": kw.get("status", ACTIVE),
        "notes": kw.get("notes", "") or "",
    }
    cur = conn.execute(
        "INSERT INTO pantry_items (user_id, %s, created_at, resolved_at)"
        " VALUES (?, %s, ?, ?)" % (", ".join(FIELDS), ", ".join("?" * len(FIELDS))),
        [user_id] + [row[f] for f in FIELDS] + [kw.get("created_at") or _now(),
                                                kw.get("resolved_at")],
    )
    return int(cur.lastrowid)


def get(conn: sqlite3.Connection, user_id: int, item_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM pantry_items WHERE id = ? AND user_id = ?", (item_id, user_id)
    ).fetchone()


def list_active(conn: sqlite3.Connection, user_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM pantry_items WHERE user_id = ? AND status = 'active'"
        " ORDER BY expiry_date ASC, id ASC",
        (user_id,),
    ).fetchall()


def list_all(conn: sqlite3.Connection, user_id: int, status: str | None = None,
             limit: int = 500) -> list[sqlite3.Row]:
    if status and status != "all":
        return conn.execute(
            "SELECT * FROM pantry_items WHERE user_id = ? AND status = ?"
            " ORDER BY COALESCE(resolved_at, created_at) DESC, id DESC LIMIT ?",
            (user_id, status, limit),
        ).fetchall()
    return conn.execute(
        "SELECT * FROM pantry_items WHERE user_id = ?"
        " ORDER BY status = 'active' DESC, expiry_date ASC LIMIT ?",
        (user_id, limit),
    ).fetchall()


def update(conn: sqlite3.Connection, user_id: int, item_id: int, **kw) -> bool:
    allowed = {
        "display_name", "grams_remaining", "storage", "container", "is_covered",
        "opened", "expiry_date", "purchase_date", "notes", "status", "resolved_at", "grams_initial",
    }
    sets, args = [], []
    for key, value in kw.items():
        if key in allowed and value is not None:
            sets.append("%s = ?" % key)
            if key in ("opened", "is_covered") and isinstance(value, bool):
                args.append(1 if value else 0)
            else:
                args.append(value)
    if not sets:
        return False
    args += [item_id, user_id]
    cur = conn.execute(
        "UPDATE pantry_items SET %s WHERE id = ? AND user_id = ?" % ", ".join(sets), args
    )
    return cur.rowcount > 0


def delete(conn: sqlite3.Connection, user_id: int, item_id: int) -> bool:
    cur = conn.execute(
        "DELETE FROM pantry_items WHERE id = ? AND user_id = ?", (item_id, user_id)
    )
    return cur.rowcount > 0


def resolve(conn: sqlite3.Connection, user_id: int, item_id: int, status: str,
            grams_remaining: float = 0.0, when: str | None = None) -> bool:
    cur = conn.execute(
        "UPDATE pantry_items SET status = ?, grams_remaining = ?, resolved_at = ?"
        " WHERE id = ? AND user_id = ? AND status = 'active'",
        (status, max(0.0, float(grams_remaining)), when or _now(), item_id, user_id),
    )
    return cur.rowcount > 0


def category_counts(conn: sqlite3.Connection, user_id: int) -> dict[str, int]:
    rows = conn.execute(
        "SELECT category, COUNT(*) AS n FROM pantry_items"
        " WHERE user_id = ? AND status = 'active' GROUP BY category",
        (user_id,),
    ).fetchall()
    return {r["category"]: int(r["n"]) for r in rows}


def food_history(conn: sqlite3.Connection, user_id: int) -> list[sqlite3.Row]:
    """Every resolved item, used by the insights engine."""
    return conn.execute(
        "SELECT * FROM pantry_items WHERE user_id = ? AND status IN"
        " ('consumed','wasted','donated') ORDER BY resolved_at DESC",
        (user_id,),
    ).fetchall()
