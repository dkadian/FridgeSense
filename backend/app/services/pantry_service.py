"""Pantry write operations.

The one piece of real subtlety is `resolve`: before an item's status changes, its
spoilage risk is scored one last time and stored on the event. That single number
is what later lets the impact page distinguish "food that was eaten" from "food
that was eaten while the model was warning about it", which is the only honest
basis for claiming the app changed an outcome.
"""
from __future__ import annotations

import datetime as dt
import sqlite3

from ..knowledge import STORAGES, Knowledge, get_knowledge
from ..repositories import events as events_repo
from ..repositories import items as items_repo
from . import impact_service, predictive_horizon, risk_service, storage_engine

VALID_STATUS = ("consumed", "wasted", "donated")


class PantryError(ValueError):
    """Raised for invalid input; routers translate this into a 400."""


def _parse_date(value, fallback: dt.date) -> dt.date:
    if not value:
        return fallback
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError as exc:
        raise PantryError("Invalid date: %r (expected YYYY-MM-DD)" % value) from exc


def resolve_grams(food, grams=None, count=None) -> float:
    if grams is not None and float(grams) > 0:
        return float(grams)
    if count is not None and float(count) > 0:
        return float(count) * float(food.grams_per_unit)
    raise PantryError("Provide either grams or count greater than zero")


def default_expiry(food, storage: str, purchase: dt.date, container: str = "default", is_covered: bool = True) -> dt.date:
    return storage_engine.calculate_expiry_date(food, storage, purchase, container, is_covered)


def add_item(conn: sqlite3.Connection, user_id: int, food_id: str, grams=None,
             count=None, storage: str | None = None, container: str | None = "default",
             is_covered: bool | None = True, purchase_date=None,
             expiry_date=None, opened: bool = False, notes: str = "",
             display_name: str | None = None, kn: Knowledge | None = None) -> dict:
    kn = kn or get_knowledge()
    food = kn.food(food_id)
    if food is None and kn.matcher:
        m = kn.matcher.match(food_id)
        if m and getattr(m, "food_id", None):
            food = kn.food(m.food_id)
    if food is None:
        matches = kn.search_foods(food_id, limit=1)
        if matches:
            food = matches[0]
    if food is None:
        raise PantryError("Unknown food: %r. Please select a valid item from the catalog." % food_id)

    storage = (storage or food.storage_default).lower()
    if storage not in STORAGES:
        raise PantryError("storage must be one of %s" % ", ".join(STORAGES))

    container = str(container or "default").lower()
    if container not in storage_engine.CONTAINERS:
        raise PantryError("container must be one of %s" % ", ".join(storage_engine.CONTAINERS))

    is_covered_val = True if is_covered is None else bool(is_covered)

    today = dt.date.today()
    purchase = _parse_date(purchase_date, today)
    grams_value = resolve_grams(food, grams, count)
    expiry = _parse_date(expiry_date, default_expiry(food, storage, purchase, container, is_covered_val))
    if expiry < purchase:
        raise PantryError("Expiry date cannot be before the purchase date")

    item_id = items_repo.create(
        conn, user_id, food_id=food.id, display_name=display_name or food.name,
        category=food.category, grams_initial=grams_value, grams_remaining=grams_value,
        storage=storage, container=container, is_covered=is_covered_val,
        opened=bool(opened), purchase_date=purchase.isoformat(),
        expiry_date=expiry.isoformat(), notes=notes,
    )
    events_repo.create(conn, user_id, item_id=item_id, food_id=food.id,
                       category=food.category, event_type="added", grams=grams_value)
    row = items_repo.get(conn, user_id, item_id)
    scored = risk_service.score_items([row], risk_service.build_context(conn, user_id), kn)
    return scored[0]


def add_many(conn: sqlite3.Connection, user_id: int, entries: list[dict],
             kn: Knowledge | None = None) -> dict:
    kn = kn or get_knowledge()
    added, failed = [], []
    for entry in entries:
        try:
            added.append(add_item(conn, user_id, kn=kn, **entry))
        except (PantryError, KeyError, TypeError) as exc:
            failed.append({"entry": entry, "error": str(exc)})
    return {"added": added, "failed": failed,
            "added_count": len(added), "failed_count": len(failed)}


def update_item(conn: sqlite3.Connection, user_id: int, item_id: int,
                kn: Knowledge | None = None, **changes) -> dict:
    kn = kn or get_knowledge()
    row = items_repo.get(conn, user_id, item_id)
    if row is None:
        raise PantryError("Item not found")
    if row["status"] != "active":
        raise PantryError("Cannot edit an item that is already %s" % row["status"])

    payload: dict = {}
    if changes.get("storage") is not None:
        storage = str(changes["storage"]).lower()
        if storage not in STORAGES:
            raise PantryError("storage must be one of %s" % ", ".join(STORAGES))
        payload["storage"] = storage

    if changes.get("container") is not None:
        c = str(changes["container"]).lower()
        if c not in storage_engine.CONTAINERS:
            raise PantryError("container must be one of %s" % ", ".join(storage_engine.CONTAINERS))
        payload["container"] = c

    if changes.get("is_covered") is not None:
        payload["is_covered"] = 1 if changes["is_covered"] else 0

    # Deterministic shelf life and expiry recalculation whenever storage or container packaging changes
    cur_container = row["container"] if "container" in row.keys() else "default"
    cur_covered = bool(row["is_covered"]) if "is_covered" in row.keys() else True
    storage_changed = (
        ("storage" in payload and payload["storage"] != row["storage"]) or
        ("container" in payload and payload["container"] != cur_container) or
        ("is_covered" in payload and payload["is_covered"] != (1 if cur_covered else 0))
    )
    if storage_changed and changes.get("expiry_date") is None:
        food = kn.food(row["food_id"])
        if food is not None:
            new_storage = payload.get("storage", row["storage"])
            new_container = payload.get("container", cur_container)
            new_covered = bool(payload.get("is_covered", 1 if cur_covered else 0))
            purchase = _parse_date(payload.get("purchase_date", row["purchase_date"]), dt.date.today())
            payload["expiry_date"] = storage_engine.calculate_expiry_date(
                food, new_storage, purchase, new_container, new_covered
            ).isoformat()
    for key in ("display_name", "notes"):
        if changes.get(key) is not None:
            payload[key] = str(changes[key])
    if changes.get("opened") is not None:
        payload["opened"] = 1 if changes["opened"] else 0
    if changes.get("grams_remaining") is not None:
        g = float(changes["grams_remaining"])
        if g < 0:
            raise PantryError("grams_remaining cannot be negative")
        payload["grams_remaining"] = g
    for key in ("expiry_date", "purchase_date"):
        if changes.get(key) is not None:
            payload[key] = _parse_date(changes[key], dt.date.today()).isoformat()

    if not payload:
        raise PantryError("No supported fields to update")
    items_repo.update(conn, user_id, item_id, **payload)
    row = items_repo.get(conn, user_id, item_id)
    return risk_service.score_items(
        [row], risk_service.build_context(conn, user_id), kn)[0]


def resolve_item(conn: sqlite3.Connection, user_id: int, item_id: int, status: str,
                 grams: float | None = None, waste_reason: str = "",
                 kn: Knowledge | None = None) -> dict:
    kn = kn or get_knowledge()
    if status not in VALID_STATUS:
        raise PantryError("status must be one of %s" % ", ".join(VALID_STATUS))
    row = items_repo.get(conn, user_id, item_id)
    if row is None:
        raise PantryError("Item not found")
    if row["status"] != "active":
        raise PantryError("Item was already marked %s" % row["status"])

    # Score before mutating, so the risk recorded is the risk the user acted on.
    scored = risk_service.score_items(
        [row], risk_service.build_context(conn, user_id), kn, explain=False)
    risk = scored[0]["risk"] if scored else None

    affected = float(row["grams_remaining"]) if grams is None else float(grams)
    affected = max(0.0, min(affected, float(row["grams_remaining"])))
    leftover = float(row["grams_remaining"]) - affected

    if leftover > 1.0 and status != "consumed":
        # Partial loss: the rest stays in the pantry rather than vanishing.
        items_repo.update(conn, user_id, item_id, grams_remaining=leftover)
        impact = impact_service.record_resolution(
            conn, user_id, row, status, affected, waste_reason, risk, kn)
        remaining_row = items_repo.get(conn, user_id, item_id)
        return {"status": "partial", "resolved_status": status, "grams": affected,
                "impact": impact, "risk_at_resolve": risk,
                "item": risk_service.score_items(
                    [remaining_row], risk_service.build_context(conn, user_id), kn)[0]}

    items_repo.resolve(conn, user_id, item_id, status, grams_remaining=0.0)
    impact = impact_service.record_resolution(
        conn, user_id, row, status, affected, waste_reason, risk, kn)
    return {"status": "resolved", "resolved_status": status, "grams": affected,
            "impact": impact, "risk_at_resolve": risk, "item": None}


def delete_item(conn: sqlite3.Connection, user_id: int, item_id: int) -> bool:
    """Removes a mis-entered row without recording any impact, unlike resolve."""
    if items_repo.get(conn, user_id, item_id) is None:
        raise PantryError("Item not found")
    conn.execute("DELETE FROM events WHERE user_id = ? AND item_id = ?", (user_id, item_id))
    return items_repo.delete(conn, user_id, item_id)


def cook_recipe(conn: sqlite3.Connection, user_id: int, recipe_id: str,
                servings: float | None = None, kn: Knowledge | None = None) -> dict:
    """Marks a recipe as cooked: deducts each ingredient it used from the pantry,
    oldest item first, and logs the consumption."""
    kn = kn or get_knowledge()
    recipe = kn.recipe_by_id.get(recipe_id)
    if recipe is None:
        raise PantryError("Unknown recipe: %r" % recipe_id)
    scale = 1.0 if not servings else max(0.25, float(servings) / float(recipe["servings"]))

    rows = items_repo.list_active(conn, user_id)
    by_food: dict[str, list] = {}
    for r in rows:
        by_food.setdefault(r["food_id"], []).append(r)
    for lst in by_food.values():           # oldest expiry first: use up the riskiest
        lst.sort(key=lambda r: str(r["expiry_date"]))

    ctx = risk_service.build_context(conn, user_id)
    used, skipped = [], []
    for ing in recipe["ingredients"]:
        need = float(ing["grams"]) * scale
        pool = by_food.get(ing["id"], [])
        if not pool:
            if not ing.get("optional"):
                skipped.append({"food_id": ing["id"], "grams": round(need, 1)})
            continue
        for row in list(pool):
            if need <= 0.01:
                break
            have = float(row["grams_remaining"])
            take = min(have, need)
            need -= take
            risk = risk_service.score_items([row], ctx, kn, explain=False)[0]["risk"]
            impact = impact_service.record_resolution(
                conn, user_id, row, "consumed", take, "", risk, kn)
            if have - take <= 1.0:
                items_repo.resolve(conn, user_id, int(row["id"]), "consumed", 0.0)
                pool.remove(row)
            else:
                items_repo.update(conn, user_id, int(row["id"]),
                                  grams_remaining=have - take)
            used.append({"food_id": row["food_id"], "name": row["display_name"],
                         "grams": round(take, 1), "risk": risk, **impact})
        if need > 1.0 and not ing.get("optional"):
            skipped.append({"food_id": ing["id"], "grams": round(need, 1)})

    return {
        "recipe_id": recipe_id,
        "title": recipe["title"],
        "servings": servings or recipe["servings"],
        "used": used,
        "short": skipped,
        "totals": {
            "grams": round(sum(u["grams"] for u in used), 1),
            "co2e_kg": round(sum(u["co2e_kg"] for u in used), 3),
            "water_l": round(sum(u["water_l"] for u in used), 1),
            "value_inr": round(sum(u["value_inr"] for u in used), 2),
            "rescued_grams": round(sum(u["grams"] for u in used if u["risk"] >= 0.45), 1),
        },
    }


def cook_custom_recipe(conn: sqlite3.Connection, user_id: int, title: str,
                       ingredients: list[dict], servings: float | None = None,
                       kn: Knowledge | None = None) -> dict:
    """Marks a custom or AI-generated recipe as cooked: deducts ingredients from pantry."""
    kn = kn or get_knowledge()
    scale = 1.0 if not servings else max(0.25, float(servings))

    rows = items_repo.list_active(conn, user_id)
    by_food: dict[str, list] = {}
    for r in rows:
        by_food.setdefault(r["food_id"], []).append(r)
    for lst in by_food.values():
        lst.sort(key=lambda r: str(r["expiry_date"]))

    ctx = risk_service.build_context(conn, user_id)
    used, skipped = [], []
    for ing in ingredients:
        fid = ing["food_id"]
        need = float(ing["grams"]) * scale
        pool = by_food.get(fid, [])
        if not pool:
            skipped.append({"food_id": fid, "grams": round(need, 1)})
            continue
        for row in list(pool):
            if need <= 0.01:
                break
            have = float(row["grams_remaining"])
            take = min(have, need)
            need -= take
            risk = risk_service.score_items([row], ctx, kn, explain=False)[0]["risk"]
            impact = impact_service.record_resolution(
                conn, user_id, row, "consumed", take, "", risk, kn)
            if have - take <= 1.0:
                items_repo.resolve(conn, user_id, int(row["id"]), "consumed", 0.0)
                pool.remove(row)
            else:
                items_repo.update(conn, user_id, int(row["id"]),
                                  grams_remaining=have - take)
            used.append({"food_id": row["food_id"], "name": row["display_name"],
                         "grams": round(take, 1), "risk": risk, **impact})
        if need > 1.0:
            skipped.append({"food_id": fid, "grams": round(need, 1)})

    return {
        "title": title,
        "servings": servings or 1.0,
        "used": used,
        "short": skipped,
        "totals": {
            "grams": round(sum(u["grams"] for u in used), 1),
            "co2e_kg": round(sum(u["co2e_kg"] for u in used), 3),
            "water_l": round(sum(u["water_l"] for u in used), 1),
            "value_inr": round(sum(u["value_inr"] for u in used), 2),
            "rescued_grams": round(sum(u["grams"] for u in used if u["risk"] >= 0.45), 1),
        },
    }



def calibrate_horizon(conn: sqlite3.Connection, user_id: int, item_id: int,
                      payload: dict, kn: Knowledge | None = None) -> dict:
    """Adjusts or marks finished a bulk staple item using predictive horizon."""
    kn = kn or get_knowledge()
    row = items_repo.get(conn, user_id, item_id)
    if row is None:
        raise PantryError("Item not found")
    action = payload.get("action", "adjust_days")
    if action == "mark_finished":
        return resolve_item(conn, user_id, item_id, "consumed", None, "", kn)

    ctx = risk_service.build_context(conn, user_id)
    food = kn.food(row["food_id"])
    horizon = predictive_horizon.compute_predictive_horizon(row, food, ctx)
    if not horizon:
        raise PantryError("Item is not a bulk staple")

    daily_burn = horizon["daily_burn_g"]
    current = float(horizon["effective_remaining_g"])
    today = dt.date.today()

    if action == "adjust_days":
        days_delta = float(payload.get("days_delta", 1.0))
        target_days = max(0.5, horizon["days_remaining"] + days_delta)
        new_remaining = round(target_days * daily_burn, 1)
    elif action == "set_days":
        target_days = max(0.5, float(payload.get("days", 2.0)))
        new_remaining = round(target_days * daily_burn, 1)
    elif action == "set_grams":
        new_remaining = max(10.0, float(payload.get("new_grams", current)))
    elif action == "reset":
        new_remaining = float(row["grams_initial"])
    else:
        raise PantryError(f"Unknown calibration action: {action}")

    # Reset baseline from today so the auto-burn curve smoothly paces from the new calibrated quantity
    items_repo.update(
        conn, user_id, item_id,
        grams_initial=new_remaining,
        grams_remaining=new_remaining,
        purchase_date=today.isoformat(),
    )
    updated = items_repo.get(conn, user_id, item_id)
    scored = risk_service.score_items([updated], ctx, kn)
    return scored[0]
