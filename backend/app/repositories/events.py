from __future__ import annotations

import datetime as dt
import sqlite3

FIELDS = (
    "item_id", "food_id", "category", "event_type", "grams", "waste_reason",
    "co2e_kg", "water_l", "value_inr", "risk_at_resolve", "occurred_at",
)


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def create(conn: sqlite3.Connection, user_id: int, **kw) -> int:
    row = {
        "item_id": kw.get("item_id"),
        "food_id": kw.get("food_id", "") or "",
        "category": kw.get("category", "") or "",
        "event_type": kw["event_type"],
        "grams": float(kw.get("grams", 0.0)),
        "waste_reason": kw.get("waste_reason", "") or "",
        "co2e_kg": float(kw.get("co2e_kg", 0.0)),
        "water_l": float(kw.get("water_l", 0.0)),
        "value_inr": float(kw.get("value_inr", 0.0)),
        "risk_at_resolve": kw.get("risk_at_resolve"),
        "occurred_at": kw.get("occurred_at") or _now(),
    }
    cur = conn.execute(
        "INSERT INTO events (user_id, %s, created_at) VALUES (?, %s, ?)"
        % (", ".join(FIELDS), ", ".join("?" * len(FIELDS))),
        [user_id] + [row[f] for f in FIELDS] + [_now()],
    )
    return int(cur.lastrowid)


def since(conn: sqlite3.Connection, user_id: int, iso_date: str,
          types: tuple[str, ...] = ()) -> list[sqlite3.Row]:
    sql = "SELECT * FROM events WHERE user_id = ? AND occurred_at >= ?"
    args: list = [user_id, iso_date]
    if types:
        sql += " AND event_type IN (%s)" % ",".join("?" * len(types))
        args += list(types)
    sql += " ORDER BY occurred_at ASC, id ASC"
    return conn.execute(sql, args).fetchall()


def recent(conn: sqlite3.Connection, user_id: int, limit: int = 40) -> list[sqlite3.Row]:
    return conn.execute(
        "SELECT * FROM events WHERE user_id = ? ORDER BY occurred_at DESC, id DESC"
        " LIMIT ?",
        (user_id, limit),
    ).fetchall()


def waste_rates(conn: sqlite3.Connection, user_id: int) -> dict:
    """Item-count waste rates overall and per category, from resolved items.

    Returned as raw counts so the caller can apply its own smoothing prior.
    """
    rows = conn.execute(
        "SELECT category, event_type, COUNT(*) AS n, SUM(grams) AS g FROM events"
        " WHERE user_id = ? AND event_type IN ('consumed','wasted','donated')"
        " GROUP BY category, event_type",
        (user_id,),
    ).fetchall()
    per: dict[str, dict[str, float]] = {}
    total = {"wasted": 0.0, "resolved": 0.0, "wasted_g": 0.0, "resolved_g": 0.0}
    for r in rows:
        cat = r["category"] or "unknown"
        d = per.setdefault(cat, {"wasted": 0.0, "resolved": 0.0,
                                 "wasted_g": 0.0, "resolved_g": 0.0})
        n, g = float(r["n"]), float(r["g"] or 0.0)
        d["resolved"] += n
        d["resolved_g"] += g
        total["resolved"] += n
        total["resolved_g"] += g
        if r["event_type"] == "wasted":
            d["wasted"] += n
            d["wasted_g"] += g
            total["wasted"] += n
            total["wasted_g"] += g
    return {"per_category": per, "total": total}


def earliest(conn: sqlite3.Connection, user_id: int) -> str | None:
    row = conn.execute(
        "SELECT MIN(occurred_at) AS m FROM events WHERE user_id = ?", (user_id,)
    ).fetchone()
    return row["m"] if row and row["m"] else None
