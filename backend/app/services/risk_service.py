"""Spoilage risk scoring.

Turns a stored pantry row into the exact feature vector the gradient-boosted
model was trained on, scores it, and converts the model's own path-based
attributions into sentences a person can act on.

The feature vector is assembled as a name -> value mapping and then ordered by
``model.feature_names_``. That ordering comes out of the saved artifact, so the
training script and this serving path cannot silently disagree about column
order - the classic way a model quietly degrades in production.
"""
from __future__ import annotations

import datetime as dt
import sqlite3

import numpy as np

from ..config import GLOBAL_WASTE_PRIOR
from ..knowledge import (STORAGE_CODE, Food, Knowledge, category_label,
                          get_knowledge)
from ..repositories import events as events_repo
from ..repositories import items as items_repo
from ..repositories import users as users_repo
from . import predictive_horizon, storage_engine

CATEGORY_PRIOR_WEIGHT = 2.0   # pseudo-observations of the global prior per category
OVERALL_PRIOR_WEIGHT = 4.0


def _date(value: str) -> dt.date:
    return dt.date.fromisoformat(str(value)[:10])


def _clip(x: float, lo: float, hi: float) -> float:
    return lo if x < lo else (hi if x > hi else x)


# --------------------------------------------------------------------- context
def build_context(conn: sqlite3.Connection, user_id: int) -> dict:
    """Everything shared across all of one user's items, fetched once."""
    user = users_repo.by_id(conn, user_id)
    household_size = float(user["household_size"]) if user else 3.0
    counts = items_repo.category_counts(conn, user_id)
    rates = events_repo.waste_rates(conn, user_id)
    total = rates["total"]
    overall = (total["wasted"] + OVERALL_PRIOR_WEIGHT * GLOBAL_WASTE_PRIOR) / (
        total["resolved"] + OVERALL_PRIOR_WEIGHT)
    per_cat = {}
    for cat, d in rates["per_category"].items():
        per_cat[cat] = (d["wasted"] + CATEGORY_PRIOR_WEIGHT * GLOBAL_WASTE_PRIOR) / (
            d["resolved"] + CATEGORY_PRIOR_WEIGHT)
    return {
        "household_size": max(1.0, household_size),
        "category_counts": counts,
        "active_items_total": float(sum(counts.values())),
        "overall_waste_rate": float(overall),
        "category_waste_rates": per_cat,
        "resolved_items": float(total["resolved"]),
    }


def feature_dict(item: sqlite3.Row | dict, food: Food, ctx: dict,
                 today: dt.date | None = None) -> dict[str, float]:
    today = today or dt.date.today()
    get = item.__getitem__

    purchase = _date(get("purchase_date"))
    expiry = _date(get("expiry_date"))
    storage = get("storage")
    grams_remaining = float(get("grams_remaining"))
    grams_initial = float(get("grams_initial")) or grams_remaining
    category = get("category") or food.category

    shelf_life_days = max(1.0, float((expiry - purchase).days))
    days_to_expiry = float((expiry - today).days)
    days_since_purchase = max(0.0, float((today - purchase).days))
    hh = float(ctx["household_size"])

    daily = max(1.0, food.daily_g_per_person) * hh
    days_of_stock = grams_initial / daily
    days_of_stock_left = grams_remaining / daily
    best_shelf = max(1.0, food.best_shelf_days)
    this_shelf = food.shelf_days(storage)
    if this_shelf <= 0:                      # storage is unsuitable for this food
        this_shelf = 0.5
    mismatch = _clip((best_shelf - this_shelf) / best_shelf, 0.0, 1.0)

    cat_rate = ctx["category_waste_rates"].get(category, GLOBAL_WASTE_PRIOR)

    return {
        "days_to_expiry": days_to_expiry,
        "shelf_life_days": shelf_life_days,
        "frac_life_remaining": _clip(days_to_expiry / shelf_life_days, -1.0, 1.0),
        "days_since_purchase": days_since_purchase,
        # Quantity is expressed relative to the pack and to this household's own
        # consumption, never as raw grams - see the note in ml/generate_dataset.py
        # on why absolute mass made the model distrust bulk staples.
        "frac_pack_remaining": _clip(grams_remaining / max(1.0, grams_initial), 0.0, 1.0),
        "days_of_stock_left": days_of_stock_left,
        "finish_ratio": _clip(days_of_stock_left / max(0.5, days_to_expiry), 0.0, 20.0),
        "storage_code": float(STORAGE_CODE.get(storage, 1)),
        "opened": 1.0 if get("opened") else 0.0,
        "perishability": float(food.perishability),
        "days_of_stock": days_of_stock,
        "stock_vs_shelf": days_of_stock / shelf_life_days,
        "storage_mismatch": mismatch,
        "same_category_count": float(ctx["category_counts"].get(category, 1)),
        "active_items_total": max(1.0, float(ctx["active_items_total"])),
        "is_leftover": 1.0 if category == "cooked_leftovers" else 0.0,
        "household_size": hh,
        "user_category_waste_rate": float(cat_rate),
        "user_overall_waste_rate": float(ctx["overall_waste_rate"]),
        # Underscore keys are context for wording and advice, not model inputs.
        # _matrix selects strictly by the artifact's feature list, so anything
        # added here can never reach the model by accident.
        "_grams_remaining": grams_remaining,
        "_grams_initial": grams_initial,
        "_grams_per_person": grams_remaining / hh,
    }


def _matrix(feature_rows: list[dict], names: list[str]) -> np.ndarray:
    return np.array([[row[n] for n in names] for row in feature_rows], dtype=np.float64)


def heuristic_risk(feats: dict) -> float:
    """Fallback if no trained artifact is present: shelf-life decay by perishability."""
    dte = max(0.0, feats["days_to_expiry"])
    base = 1.0 / (1.0 + dte)
    per = (feats["perishability"] - 1.0) / 4.0
    return float(_clip(0.65 * base + 0.25 * per + 0.10 * feats["opened"], 0.0, 1.0))


def _days_phrase(days: float) -> str:
    """Days of eating, in words a person would use rather than 0.6 days."""
    if days < 0.75:
        return "half a day"
    if days < 1.4:
        return "a day"
    if days < 2.5:
        return "two days"
    if days < 6.5:
        return "%d days" % int(round(days))
    if days < 10.5:
        return "about a week"
    if days < 45:
        return "about %d weeks" % int(round(days / 7.0))
    return "months"


# ------------------------------------------------------------------ explaining
# Features that express the same idea to a human. Only the highest-attribution
# member of each group becomes a bullet, so the card never says "expires today"
# and "0% of its life is left" as if they were two separate findings.
CONCEPT_GROUPS = {
    "days_to_expiry": "clock",
    "frac_life_remaining": "clock",
    "shelf_life_days": "clock",
    "days_since_purchase": "clock",
    "finish_ratio": "quantity",
    "days_of_stock_left": "quantity",
    "days_of_stock": "portion",
    "stock_vs_shelf": "portion",
    "frac_pack_remaining": "portion",
    "user_category_waste_rate": "habit",
    "user_overall_waste_rate": "habit",
    "same_category_count": "crowding",
    "active_items_total": "crowding",
}


def _phrase(name: str, feats: dict, food: Food, storage: str,
            reduces: bool = False) -> str | None:
    """Render one feature as a sentence, or None if no honest sentence exists.

    A boosted tree can push a feature either way depending on the path taken, so
    every branch here checks that the wording agrees with the sign of the
    contribution. When it does not, the reason is dropped rather than shown with
    a label that contradicts it.
    """
    v = feats[name]

    if name == "days_to_expiry":
        if v < 0:
            n = abs(int(v))
            return "Best-before was %d day%s ago" % (n, "" if n == 1 else "s")
        if v == 0:
            return "Best-before is today"
        if reduces and v >= 3:
            return "Still %d days of shelf life left" % int(v)
        return "%d day%s of shelf life left" % (int(v), "" if int(v) == 1 else "s")

    if name == "frac_life_remaining":
        pct = max(0, round(v * 100))
        return ("Still %d%% of its life to go" % pct) if reduces else (
            "Only %d%% of its life is left" % pct)

    if name == "shelf_life_days":
        return "Total shelf life is only %d days" % int(v) if not reduces else None

    if name == "days_since_purchase":
        return None if reduces else "In the kitchen for %d days already" % int(v)

    if name == "stock_vs_shelf":
        if v > 1.0 and not reduces:
            return ("You bought about %.1f days of %s but it only keeps for %d days"
                    % (feats["days_of_stock"], food.name.lower(),
                       int(feats["shelf_life_days"])))
        if v <= 1.0 and reduces:
            return "The quantity fits comfortably inside the shelf life"
        return None

    if name == "days_of_stock":
        if reduces and feats["days_of_stock"] <= 2.0:
            return "Only about %.1f days of eating - easy to finish" % feats["days_of_stock"]
        if not reduces:
            return "That is roughly %.1f days of eating for your household" % feats["days_of_stock"]
        return None

    if name == "perishability":
        if v >= 4 and not reduces:
            return "%s is highly perishable" % food.name
        if v <= 2 and reduces:
            return "%s keeps well" % food.name
        return None

    if name == "storage_mismatch":
        rec, rec_days = food.recommended_storage, int(food.recommended_shelf_days)
        here = int(max(1, food.shelf_days(storage)))
        if not reduces and rec != storage and rec_days > here + 1:
            return ("Stored in the %s - the %s would give it %d days instead of %d"
                    % (storage, rec, rec_days, here))
        if not reduces and food.freezer_gain(storage) >= 14:
            return ("Only the freezer would extend it much further (about %d days)"
                    % int(food.shelf_days("freezer")))
        if reduces and rec == storage:
            return "Stored in the best place for it"
        return None

    if name == "opened":
        if v and not reduces:
            return "The pack is already open"
        if not v and reduces:
            return "Still sealed"
        return None

    if name == "finish_ratio":
        # Days of eating left, over days left to eat it. The single most useful
        # sentence the model produces, so it is worded carefully.
        if v > 1.15 and not reduces:
            return ("More here than you would normally eat before the date - about "
                    "%s worth, with %d day%s to go"
                    % (_days_phrase(feats["days_of_stock_left"]),
                       max(0, int(feats["days_to_expiry"])),
                       "" if int(feats["days_to_expiry"]) == 1 else "s"))
        if v <= 0.7 and reduces:
            return "Easily finished in the time left"
        return None

    if name == "days_of_stock_left":
        if reduces and v <= 1.2:
            return "Only about %s of eating left" % _days_phrase(v)
        if not reduces and v >= 2.0:
            return "That is roughly %s of eating for your household" % _days_phrase(v)
        return None

    if name == "frac_pack_remaining":
        pct = int(round(v * 100))
        if not reduces and v >= 0.8:
            return "Barely touched - %d%% of it is still there" % pct
        if reduces and v <= 0.4:
            return "Mostly eaten already, only %d%% left" % pct
        return None

    if name == "same_category_count":
        label = feats.get("_category_label", "similar")
        if v >= 3 and not reduces:
            return "You have %d other %s items competing for attention" % (int(v) - 1, label)
        if v <= 2 and reduces:
            return "Not much else in the %s shelf to distract you" % label
        return None

    if name == "active_items_total":
        # This counts items being tracked, not packs that have been opened. An
        # earlier wording said "open", which was simply untrue.
        if v >= 12 and not reduces:
            return ("You are keeping track of %d items - things get lost in a full "
                    "kitchen" % int(v))
        if v < 12 and reduces:
            return "Not many items to keep track of (%d), so little gets lost" % int(v)
        return None

    if name in ("user_category_waste_rate", "user_overall_waste_rate"):
        scope = "this category" if name.startswith("user_category") else "overall"
        pct = round(v * 100)
        if not reduces:
            return "You have historically wasted %d%% %s" % (pct, scope)
        return "You rarely waste %s (%d%%)" % (scope, pct)

    if name == "is_leftover":
        return "Cooked leftovers get forgotten fast" if (v and not reduces) else None

    return None


# Within a concept group, some features simply explain themselves better. Days to
# expiry beats fraction-of-life-remaining: "best-before was 1 day ago" tells you
# something, "0% of its life is left" makes you work it out. Attribution order
# alone picked the wrong one, so the preference is stated explicitly.
GROUP_PREFERRED = {"clock": "days_to_expiry"}


# True of the whole kitchen rather than of this item: the same sentence would
# appear on every card, which tells the reader nothing about why *this* food is at
# the top of the list. They still influence the score - a crowded kitchen really
# does lose more food - but at most one is allowed to appear as a reason, and only
# once the item-specific ones have run out. Household-level patterns are the job
# of the insights view, which can say them once instead of thirty times.
CONTEXT_FEATURES = {
    "active_items_total",
    "same_category_count",
    "household_size",
    "user_overall_waste_rate",
    "user_category_waste_rate",
}
MAX_CONTEXT_REASONS = 1


def _order_attributions(attrs: list[dict]) -> list[dict]:
    """Promote each group's preferred feature without disturbing group ranking.

    Groups keep the order in which they first appear, so the strongest concept
    still leads; only the choice of spokesman within a group changes.
    """
    by_group: dict[str, list[dict]] = {}
    for a in attrs:
        by_group.setdefault(CONCEPT_GROUPS.get(a["feature"], a["feature"]), []).append(a)

    ordered: list[dict] = []
    for group, members in by_group.items():
        preferred = GROUP_PREFERRED.get(group)
        pick = next((m for m in members if m["feature"] == preferred), members[0])
        ordered.append(pick)
        ordered.extend(m for m in members if m is not pick)   # fallbacks kept
    return ordered


# "Cook it today" is wrong for a litre of milk and odd for an apple, so the verb
# follows the food. Anything not listed falls back to cooking, which is the right
# default for vegetables, pulses, grains, meat and eggs.
URGENT_VERB = {
    "fruits": "Eat", "bakery": "Eat", "snacks": "Eat",
    "dairy": "Use", "beverages": "Drink", "condiments": "Use",
    "cooked_leftovers": "Finish",
}


def _urgent_action(category: str, today: bool) -> str:
    verb = URGENT_VERB.get(category, "Cook")
    return "%s it today" % verb if today else "%s it in the next two days" % verb


def _worth_freezing(feats: dict, food: Food, storage: str, score: float,
                    days_to_expiry: float) -> bool:
    """Freezing is only advice worth giving when there is a surplus to freeze.

    Two guards, both learned from reading the output. Telling someone to freeze
    50 g of fenugreek that one meal would clear is noise, so the quantity has to
    exceed what the household could plausibly eat before the date. And food
    already past its date should be checked, not frozen - freezing preserves
    whatever state it is in, including spoiled.
    """
    if score < 0.45 or days_to_expiry < 0 or food.freezer_gain(storage) < 14:
        return False
    days_left = max(1.0, min(days_to_expiry, 3.0))
    eatable = food.daily_g_per_person * max(1.0, feats["household_size"]) * days_left
    return feats["_grams_remaining"] > 1.2 * max(1.0, eatable)


def _actions(feats: dict, food: Food, storage: str, score: float,
             days_to_expiry: float = 99.0) -> list[str]:
    """Concrete next steps, gated on risk so a safe item is not given busywork.

    Order is by urgency, not by how clever the suggestion is. An earlier version
    put storage advice first and told the owner of a day-old cooked dal to freeze
    it, when the answer is to eat it tonight. Freezing and repurchase advice are
    real but secondary; they only lead when there is still time to act on them.
    """
    out: list[str] = []
    low_risk = score < 0.22
    rec = food.recommended_storage
    gain = int(food.recommended_shelf_days - max(1, food.shelf_days(storage)))
    can_move = rec != storage and gain >= 2

    # 1. Urgency first.
    if days_to_expiry < 0:
        out.append("Past its date - check it before you trust it")
    elif score >= 0.7:
        out.append(_urgent_action(food.category, today=True))
    elif score >= 0.45:
        out.append(_urgent_action(food.category, today=False))

    # 2. Leftovers have an obvious cheap answer.
    if feats["is_leftover"] and score >= 0.30:
        out.append("Reheat it for lunch tomorrow rather than cooking something new")

    # 3. Storage, but only while a move would still buy useful time.
    if not low_risk and can_move and days_to_expiry >= 0:
        out.append("Move it to the %s (+%d days)" % (rec, gain))
    elif not low_risk and _worth_freezing(feats, food, storage, score, days_to_expiry):
        out.append("Freeze what you cannot finish - it keeps for about %d days"
                   % int(food.shelf_days("freezer")))
    if score >= 0.30 and days_to_expiry <= 7 and \
            feats["_grams_per_person"] > 2.5 * max(1.0, food.daily_g_per_person):
        out.append("Portion and freeze half, or share it")
    if feats["stock_vs_shelf"] > 1.4:
        suggested = food.daily_g_per_person * feats["household_size"] * min(
            feats["shelf_life_days"], 7.0)
        step = 50 if suggested < 500 else 250
        out.append("Next time buy about %d g instead of %d g" % (
            max(step, int(round(suggested / step) * step)),
            int(feats["_grams_initial"])))
    if not out:
        out.append("Nothing to do - it is comfortably within its life" if low_risk
                   else "Keep it in view and plan a meal around it this week")
    return out[:3]


# --------------------------------------------------------------------- scoring
def score_items(rows: list, ctx: dict, kn: Knowledge | None = None,
                today: dt.date | None = None, explain: bool = True) -> list[dict]:
    """Score a batch of pantry rows. One model call for the whole batch."""
    kn = kn or get_knowledge()
    today = today or dt.date.today()
    if not rows:
        return []

    prepared = []
    for row in rows:
        food = kn.food(row["food_id"])
        if food is None:                     # unknown food id: synthesise a safe stub
            food = Food(id=row["food_id"], name=row["display_name"],
                        category=row["category"] or "other", perishability=3,
                        storage_default=row["storage"],
                        shelf={"pantry": 5.0, "fridge": 7.0, "freezer": 60.0})
        feats = feature_dict(row, food, ctx, today)
        prepared.append((row, food, feats))

    model = kn.model
    if model is not None:
        names = list(model.feature_names_)
        X = _matrix([f for _, _, f in prepared], names)
        scores = model.predict_proba(X)
    else:
        names = []
        scores = np.array([heuristic_risk(f) for _, _, f in prepared])

    # Map storage zone -> active items to detect ethylene co-location conflicts
    storage_active: dict[str, list[tuple]] = {}
    for r, f, _ in prepared:
        storage_active.setdefault(r["storage"], []).append((r, f))

    out = []
    for idx, (row, food, feats) in enumerate(prepared):
        score = float(_clip(float(scores[idx]), 0.0, 1.0))
        horizon = predictive_horizon.compute_predictive_horizon(row, food, ctx, today)
        effective_grams = horizon["effective_remaining_g"] if horizon else round(float(row["grams_remaining"]), 1)
        kg = float(effective_grams) / 1000.0
        reasons: list[dict] = []

        # Storage Co-Pilot: Ethylene gas conflict detection
        item_storage = row["storage"]
        colocated = storage_active.get(item_storage, [])
        ethylene_conflict = {
            "has_conflict": False,
            "type": food.ethylene_type,
            "conflicting_with": [],
            "tip": food.ethylene_tip,
        }

        if food.ethylene_type == "sensitive":
            producers = [
                (r2["display_name"] if ("display_name" in r2.keys() and r2["display_name"]) else f2.name)
                for r2, f2 in colocated
                if f2.id in food.ethylene_antagonists and r2["id"] != row["id"]
            ]
            if producers:
                prod_names = sorted(list(set(producers)))
                # Accelerate decay risk slightly due to active ethylene exposure
                score = float(_clip(score + 0.07, 0.0, 1.0))
                ethylene_conflict["has_conflict"] = True
                ethylene_conflict["conflicting_with"] = prod_names
                if explain:
                    reasons.append({
                        "feature": "storage_mismatch",
                        "text": "Ethylene alert: Stored with %s in the %s, accelerating decay"
                                % (", ".join(prod_names[:2]), item_storage),
                        "direction": "increases",
                        "contribution": 0.07,
                    })

        elif food.ethylene_type == "producer":
            sensitive_targets = [
                (r2["display_name"] if ("display_name" in r2.keys() and r2["display_name"]) else f2.name)
                for r2, f2 in colocated
                if f2.ethylene_type == "sensitive" and food.id in f2.ethylene_antagonists and r2["id"] != row["id"]
            ]
            if sensitive_targets:
                sens_names = sorted(list(set(sensitive_targets)))
                ethylene_conflict["has_conflict"] = True
                ethylene_conflict["conflicting_with"] = sens_names

        # Storage & Packaging Co-Pilot
        item_container = row["container"] if "container" in row.keys() and row["container"] else "default"
        item_covered = bool(row["is_covered"]) if "is_covered" in row.keys() and row["is_covered"] is not None else True
        pkg_insight = storage_engine.get_packaging_insight(food, row["storage"], item_container, item_covered)

        if pkg_insight["tone"] == "positive":
            score = float(_clip(score - 0.05, 0.0, 1.0))
        elif pkg_insight["tone"] == "negative":
            score = float(_clip(score + 0.07, 0.0, 1.0))

        band = kn.band_for(score)

        if explain and model is not None:
            feats["_category_label"] = category_label(row["category"] or food.category)
            seen_groups: set[str] = set()
            specific: list[dict] = []
            context: list[dict] = []
            for attr in _order_attributions(model.explain(X[idx], top_k=12)):
                group = CONCEPT_GROUPS.get(attr["feature"], attr["feature"])
                if group in seen_groups:
                    continue
                text = _phrase(attr["feature"], feats, food, row["storage"],
                               reduces=attr["contribution"] < 0)
                if not text:
                    continue
                seen_groups.add(group)
                bucket = context if attr["feature"] in CONTEXT_FEATURES else specific
                bucket.append({
                    "feature": attr["feature"],
                    "text": text,
                    "direction": "increases" if attr["contribution"] > 0 else "reduces",
                    "contribution": round(float(attr["contribution"]), 4),
                })
            # Combine model-derived reasons with storage & packaging co-pilot alerts
            if pkg_insight["tone"] == "positive":
                reasons.append({
                    "feature": "container",
                    "text": f"{pkg_insight['badge_text']}: {pkg_insight['advice']}",
                    "direction": "reduces",
                    "contribution": -0.05,
                })
            elif pkg_insight["tone"] == "negative":
                reasons.append({
                    "feature": "container",
                    "text": f"{pkg_insight['badge_text']}: {pkg_insight['advice']}",
                    "direction": "increases",
                    "contribution": 0.07,
                })
            reasons = (reasons + specific + context[:MAX_CONTEXT_REASONS])[:4]

        item_actions = _actions(feats, food, row["storage"], score, feats["days_to_expiry"])
        if pkg_insight["tone"] == "negative":
            item_actions.insert(0, pkg_insight["advice"])

        if ethylene_conflict["has_conflict"]:
            if food.ethylene_type == "sensitive":
                item_actions.insert(0, "Separate from %s (use a sealed container or separate shelf)"
                                       % ethylene_conflict["conflicting_with"][0])
            elif food.ethylene_type == "producer":
                item_actions.insert(0, "Keep away from %s — %s emits ethylene gas that spoils it faster"
                                       % (ethylene_conflict["conflicting_with"][0], food.name))

        out.append({
            "item_id": int(row["id"]),
            "food_id": food.id,
            "name": row["display_name"],
            "category": row["category"] or food.category,
            "storage": row["storage"],
            "container": item_container,
            "container_label": storage_engine.CONTAINER_LABELS.get(item_container, item_container),
            "is_covered": item_covered,
            "packaging_insight": pkg_insight,
            "opened": bool(row["opened"]),
            "grams_remaining": round(float(effective_grams), 1),
            "purchase_date": str(row["purchase_date"])[:10],
            "created_at": str(row["created_at"])[:10] if ("created_at" in row.keys() and row["created_at"]) else str(row["purchase_date"])[:10],
            "days_since_purchase": int(feats.get("days_since_purchase", 0)),
            "expiry_date": str(row["expiry_date"])[:10],
            "days_to_expiry": int(feats["days_to_expiry"]),
            "risk": round(score, 4),
            "risk_band": band["band"],
            "risk_label": band.get("label", band["band"]),
            "risk_color": band.get("color", "#888888"),
            "at_risk_co2e_kg": round(score * kg * food.co2e_kg_per_kg, 4),
            "at_risk_water_l": round(score * kg * food.water_l_per_kg, 1),
            "at_risk_value_inr": round(score * kg * food.price_inr_per_kg, 2),
            "embodied_co2e_kg": round(kg * food.co2e_kg_per_kg, 4),
            "embodied_value_inr": round(kg * food.price_inr_per_kg, 2),
            "best_storage": food.best_storage,
            "reasons": reasons,
            "actions": item_actions[:3],
            "ethylene_co_pilot": ethylene_conflict,
            "predictive_horizon": horizon,
        })
    return out


def score_pantry(conn: sqlite3.Connection, user_id: int, kn: Knowledge | None = None,
                 today: dt.date | None = None) -> list[dict]:
    kn = kn or get_knowledge()
    ctx = build_context(conn, user_id)
    rows = items_repo.list_active(conn, user_id)
    scored = score_items(rows, ctx, kn, today)
    # Prioritize items that actually have edible food remaining over 0g ghost rows
    scored.sort(key=lambda s: (s["grams_remaining"] <= 0, -s["risk"], s["days_to_expiry"]))
    return scored


def risk_for_item(conn: sqlite3.Connection, user_id: int, item_id: int,
                  kn: Knowledge | None = None) -> dict | None:
    row = items_repo.get(conn, user_id, item_id)
    if row is None:
        return None
    ctx = build_context(conn, user_id)
    scored = score_items([row], ctx, kn or get_knowledge())
    return scored[0] if scored else None


def pantry_summary(scored: list[dict], kn: Knowledge | None = None) -> dict:
    kn = kn or get_knowledge()
    bands = {b["band"]: 0 for b in kn.risk_bands()}
    for s in scored:
        bands[s["risk_band"]] = bands.get(s["risk_band"], 0) + 1
    at_risk = [s for s in scored if s["risk"] >= 0.45 and s["grams_remaining"] > 0]

    # Group staples by food_id to assess household-wide real stock
    staples_by_food: dict[str, list[dict]] = {}
    for s in scored:
        if s.get("predictive_horizon"):
            fid = s["food_id"]
            staples_by_food.setdefault(fid, []).append(s)

    staples_near_empty = []
    for fid, batch_items in staples_by_food.items():
        total_effective_g = sum(b["predictive_horizon"]["effective_remaining_g"] for b in batch_items)
        daily_burn = batch_items[0]["predictive_horizon"]["daily_burn_g"]
        total_days_remaining = total_effective_g / daily_burn if daily_burn > 0 else 0.0

        # Only flag if total household stock of this staple is critically low
        if total_days_remaining <= 1.5:
            # Pick representative item
            rep_item = dict(min(batch_items, key=lambda b: b["predictive_horizon"]["effective_remaining_g"]))
            rep_horizon = dict(rep_item["predictive_horizon"])
            rep_horizon["effective_remaining_g"] = round(total_effective_g, 1)
            rep_horizon["days_remaining"] = round(total_days_remaining, 1)
            rep_item["predictive_horizon"] = rep_horizon
            rep_item["grams_remaining"] = round(total_effective_g, 1)
            staples_near_empty.append(rep_item)

    return {
        "items_active": len(scored),
        "band_counts": bands,
        "items_at_risk": len(at_risk),
        "staples_tracked_count": len(staples_by_food),
        "staples_near_empty": staples_near_empty,
        "expected_loss_kg": round(sum(s["risk"] * s["grams_remaining"] for s in scored) / 1000.0, 3),
        "expected_loss_co2e_kg": round(sum(s["at_risk_co2e_kg"] for s in scored), 3),
        "expected_loss_water_l": round(sum(s["at_risk_water_l"] for s in scored), 1),
        "expected_loss_inr": round(sum(s["at_risk_value_inr"] for s in scored), 2),
        "pantry_value_inr": round(sum(s["embodied_value_inr"] for s in scored), 2),
        "pantry_co2e_kg": round(sum(s["embodied_co2e_kg"] for s in scored), 3),
    }
