"""Environmental accounting.

Being precise about what a number means matters more here than making it large,
so this module reports three separate quantities and never blends them:

1. Waste footprint - the embodied CO2e, water and money of food this household
   actually threw away. A cost that really was incurred.

2. Avoided versus baseline - the counterfactual. If the household had wasted
   food at the global household rate of 22% by mass (UNEP Food Waste Index
   Report 2024), how much would it have thrown away?

   The comparison is restricted to perishable food, meaning items whose
   recommended storage keeps them for 60 days or less. A 5 kg sack of rice and a
   bunch of coriander are not comparable risks, and household waste in the UNEP
   figure is overwhelmingly perishable. Left unrestricted, a shopper who buys
   staples in bulk gets a large denominator and appears to beat the baseline by
   doing nothing at all - the rate falls simply because rice does not rot. So
   both sides of this particular comparison drop staples, while the reported
   waste footprint above still counts every gram.

   Mass converts to CO2e using this household's own realised intensity over the
   same perishable subset (kg CO2e per kg handled), which keeps the arithmetic
   internally consistent with the real basket rather than a generic average. The
   number goes negative when a household is doing worse than the baseline, and
   it is reported that way rather than floored at zero.

3. Rescued at the edge - food eaten while the model rated it high risk (0.45 and
   above, the "use in 1-2 days" band), which is why every event stores the risk
   score as it stood at resolution time.

   This is descriptive, not causal. Some of that food would have been eaten
   anyway; a bunch of spinach bought on Sunday and cooked on Thursday is normal
   shopping, not a narrow escape. So it is reported as "eaten while flagged",
   never as an amount the app saved, and it is never added to the avoided total
   in note 2 - doing so would count the same kilogram twice under two different
   theories of what would otherwise have happened.

Emission and water intensities come from Poore & Nemecek (2018) and Mekonnen &
Hoekstra (2011); see data/impact_factors.json for the full source list.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from collections import defaultdict

from ..config import GLOBAL_WASTE_PRIOR
from ..knowledge import Knowledge, category_title, get_knowledge
from ..repositories import events as events_repo

RESOLVING = ("consumed", "wasted", "donated")
RESCUE_RISK_THRESHOLD = 0.45

# Above this recommended shelf life a food counts as a staple and is excluded
# from the baseline comparison (never from the waste footprint itself).
PERISHABLE_MAX_SHELF_DAYS = 60


def _is_perishable(food_id: str, kn: Knowledge) -> bool:
    food = kn.food(food_id)
    if food is None:
        return True          # unknown foods are assumed perishable, not staples
    return food.recommended_shelf_days <= PERISHABLE_MAX_SHELF_DAYS


def _window_start(days: int) -> dt.date:
    return dt.date.today() - dt.timedelta(days=max(1, int(days)) - 1)


def equivalences(co2e_kg: float, water_l: float, kn: Knowledge) -> list[dict]:
    """Human-scale comparisons. Each carries its own conversion factor so the
    frontend never has to hard-code one."""
    co2e_kg = max(0.0, float(co2e_kg))
    water_l = max(0.0, float(water_l))
    km = co2e_kg * kn.equivalence("car_km_per_kg_co2e", 5.208)
    showers = water_l / max(1.0, kn.equivalence("shower_litres", 65.0))
    charges = co2e_kg / max(1e-9, kn.equivalence("phone_charge_kg_co2e", 0.0084))
    tree_days = co2e_kg / max(1e-9, kn.equivalence(
        "tree_kg_co2e_absorbed_per_year", 21.0)) * 365.0
    bulb_hours = co2e_kg * kn.equivalence("led_bulb_hours_per_kg_co2e", 1875.0)
    return [
        {"key": "car_km", "value": round(km, 1), "unit": "km",
         "label": "car travel avoided", "icon": "car"},
        {"key": "showers", "value": round(showers, 1), "unit": "showers",
         "label": "8-minute showers of water", "icon": "droplet"},
        {"key": "phone_charges", "value": int(round(charges)), "unit": "charges",
         "label": "phone charges", "icon": "battery"},
        {"key": "tree_days", "value": round(tree_days, 1), "unit": "tree-days",
         "label": "of a tree's yearly absorption", "icon": "tree"},
        {"key": "bulb_hours", "value": int(round(bulb_hours)), "unit": "hours",
         "label": "of LED bulb runtime", "icon": "bulb"},
    ]


def _empty_totals() -> dict:
    return {"grams": 0.0, "co2e_kg": 0.0, "water_l": 0.0, "value_inr": 0.0, "count": 0}


def _accumulate(bucket: dict, row) -> None:
    bucket["grams"] += float(row["grams"])
    bucket["co2e_kg"] += float(row["co2e_kg"])
    bucket["water_l"] += float(row["water_l"])
    bucket["value_inr"] += float(row["value_inr"])
    bucket["count"] += 1


def _round(bucket: dict) -> dict:
    return {
        "grams": round(bucket["grams"], 1),
        "kg": round(bucket["grams"] / 1000.0, 3),
        "co2e_kg": round(bucket["co2e_kg"], 3),
        "water_l": round(bucket["water_l"], 1),
        "value_inr": round(bucket["value_inr"], 2),
        "count": int(bucket["count"]),
    }


def summary(conn: sqlite3.Connection, user_id: int, days: int = 30,
            kn: Knowledge | None = None) -> dict:
    kn = kn or get_knowledge()
    start = _window_start(days)
    rows = events_repo.since(conn, user_id, start.isoformat(), RESOLVING)

    wasted, consumed, donated, rescued = (_empty_totals() for _ in range(4))
    p_wasted, p_handled = _empty_totals(), _empty_totals()
    for r in rows:
        if r["event_type"] == "wasted":
            _accumulate(wasted, r)
        elif r["event_type"] == "donated":
            _accumulate(donated, r)
        else:
            _accumulate(consumed, r)
            risk = r["risk_at_resolve"]
            if risk is not None and float(risk) >= RESCUE_RISK_THRESHOLD:
                _accumulate(rescued, r)
        if _is_perishable(r["food_id"], kn):
            _accumulate(p_handled, r)
            if r["event_type"] == "wasted":
                _accumulate(p_wasted, r)

    handled_g = wasted["grams"] + consumed["grams"] + donated["grams"]
    handled_co2e = wasted["co2e_kg"] + consumed["co2e_kg"] + donated["co2e_kg"]
    handled_water = wasted["water_l"] + consumed["water_l"] + donated["water_l"]
    handled_value = wasted["value_inr"] + consumed["value_inr"] + donated["value_inr"]

    waste_rate = (wasted["grams"] / handled_g) if handled_g > 0 else 0.0

    # The counterfactual, on perishables only - see note 2 in the module docstring.
    ph_g = p_handled["grams"]
    perishable_rate = (p_wasted["grams"] / ph_g) if ph_g > 0 else 0.0
    baseline_g = GLOBAL_WASTE_PRIOR * ph_g
    avoided_g = baseline_g - p_wasted["grams"]

    # Realised intensity of the perishable basket, so mass converts consistently.
    per_kg_co2e = (p_handled["co2e_kg"] / ph_g * 1000.0) if ph_g > 0 else 0.0
    per_kg_water = (p_handled["water_l"] / ph_g * 1000.0) if ph_g > 0 else 0.0
    per_kg_value = (p_handled["value_inr"] / ph_g * 1000.0) if ph_g > 0 else 0.0

    avoided = {
        "grams": round(avoided_g, 1),
        "kg": round(avoided_g / 1000.0, 3),
        "co2e_kg": round(avoided_g / 1000.0 * per_kg_co2e, 3),
        "water_l": round(avoided_g / 1000.0 * per_kg_water, 1),
        "value_inr": round(avoided_g / 1000.0 * per_kg_value, 2),
        "beats_baseline": bool(avoided_g > 0),
    }

    meal_grams = max(1.0, kn.equivalence("meal_grams", 420.0))
    return {
        "window_days": int(days),
        "window_start": start.isoformat(),
        "window_end": dt.date.today().isoformat(),
        "wasted": _round(wasted),
        "consumed": _round(consumed),
        "donated": _round(donated),
        "rescued": _round(rescued),
        "handled": {
            "grams": round(handled_g, 1), "kg": round(handled_g / 1000.0, 3),
            "co2e_kg": round(handled_co2e, 3), "value_inr": round(handled_value, 2),
            "items": len(rows),
        },
        "waste_rate": round(waste_rate, 4),
        "perishable": {
            "handled_kg": round(ph_g / 1000.0, 3),
            "wasted_kg": round(p_wasted["grams"] / 1000.0, 3),
            "waste_rate": round(perishable_rate, 4),
            "max_shelf_days": PERISHABLE_MAX_SHELF_DAYS,
        },
        "baseline_waste_rate": GLOBAL_WASTE_PRIOR,
        "baseline_wasted_grams": round(baseline_g, 1),
        "baseline_basis": (
            "UNEP Food Waste Index 2024 household rate of 22% by mass, applied to "
            "perishable food only (recommended shelf life <= "
            f"{PERISHABLE_MAX_SHELF_DAYS} days) so bulk staples cannot flatter the "
            "comparison."
        ),
        "avoided_vs_baseline": avoided,
        "intensity": {
            "co2e_kg_per_kg": round(per_kg_co2e, 3),
            "water_l_per_kg": round(per_kg_water, 1),
            "inr_per_kg": round(per_kg_value, 2),
        },
        "meals_saved": round((consumed["grams"] + donated["grams"]) / meal_grams, 1),
        "meals_lost": round(wasted["grams"] / meal_grams, 1),
        "equivalences_avoided": equivalences(avoided["co2e_kg"], avoided["water_l"], kn),
        "equivalences_wasted": equivalences(wasted["co2e_kg"], wasted["water_l"], kn),
        "sources": kn.factors.get("sources", []),
    }


def timeseries(conn: sqlite3.Connection, user_id: int, days: int = 30,
               kn: Knowledge | None = None) -> dict:
    kn = kn or get_knowledge()
    start = _window_start(days)
    rows = events_repo.since(conn, user_id, start.isoformat(), RESOLVING)

    per_day: dict[str, dict] = {}
    for i in range(max(1, int(days))):
        key = (start + dt.timedelta(days=i)).isoformat()
        per_day[key] = {"date": key, "wasted_g": 0.0, "consumed_g": 0.0,
                        "wasted_co2e_kg": 0.0, "wasted_inr": 0.0, "rescued_g": 0.0}
    for r in rows:
        key = str(r["occurred_at"])[:10]
        if key not in per_day:
            continue
        d = per_day[key]
        if r["event_type"] == "wasted":
            d["wasted_g"] += float(r["grams"])
            d["wasted_co2e_kg"] += float(r["co2e_kg"])
            d["wasted_inr"] += float(r["value_inr"])
        else:
            d["consumed_g"] += float(r["grams"])
            risk = r["risk_at_resolve"]
            if r["event_type"] == "consumed" and risk is not None and \
                    float(risk) >= RESCUE_RISK_THRESHOLD:
                d["rescued_g"] += float(r["grams"])

    series = [per_day[k] for k in sorted(per_day)]
    # Seven-day trailing waste rate: noisy daily rates are not worth plotting.
    window: list[tuple[float, float]] = []
    for d in series:
        window.append((d["wasted_g"], d["wasted_g"] + d["consumed_g"]))
        if len(window) > 7:
            window.pop(0)
        w = sum(x[0] for x in window)
        t = sum(x[1] for x in window)
        d["waste_rate_7d"] = round(w / t, 4) if t > 0 else None
        for k in ("wasted_g", "consumed_g", "rescued_g"):
            d[k] = round(d[k], 1)
        d["wasted_co2e_kg"] = round(d["wasted_co2e_kg"], 3)
        d["wasted_inr"] = round(d["wasted_inr"], 2)

    zero_streak = 0
    for d in reversed(series):
        if d["wasted_g"] > 0:
            break
        zero_streak += 1
    return {"series": series, "zero_waste_streak_days": zero_streak,
            "baseline_waste_rate": GLOBAL_WASTE_PRIOR}


def breakdown(conn: sqlite3.Connection, user_id: int, days: int = 90,
              kn: Knowledge | None = None) -> dict:
    kn = kn or get_knowledge()
    start = _window_start(days)
    rows = events_repo.since(conn, user_id, start.isoformat(), RESOLVING)

    by_cat: dict[str, dict] = defaultdict(
        lambda: {"wasted": _empty_totals(), "resolved": _empty_totals()})
    by_food: dict[str, dict] = defaultdict(lambda: _empty_totals())
    by_reason: dict[str, dict] = defaultdict(lambda: _empty_totals())

    for r in rows:
        cat = r["category"] or "unknown"
        _accumulate(by_cat[cat]["resolved"], r)
        if r["event_type"] == "wasted":
            _accumulate(by_cat[cat]["wasted"], r)
            _accumulate(by_food[r["food_id"]], r)
            _accumulate(by_reason[r["waste_reason"] or "unspecified"], r)

    categories = []
    for cat, d in by_cat.items():
        res = d["resolved"]["grams"]
        categories.append({
            "category": cat,
            "label": category_title(cat),
            "wasted": _round(d["wasted"]),
            "resolved": _round(d["resolved"]),
            "waste_rate": round(d["wasted"]["grams"] / res, 4) if res > 0 else 0.0,
        })
    categories.sort(key=lambda c: -c["wasted"]["co2e_kg"])

    foods = []
    for fid, d in by_food.items():
        food = kn.food(fid)
        foods.append({"food_id": fid, "name": food.name if food else fid, **_round(d)})
    foods.sort(key=lambda f: -f["co2e_kg"])

    total_reason_g = sum(d["grams"] for d in by_reason.values()) or 1.0
    reasons = [
        {"reason": k, "label": k.replace("_", " ").capitalize(),
         "share": round(d["grams"] / total_reason_g, 4), **_round(d)}
        for k, d in by_reason.items()
    ]
    reasons.sort(key=lambda r: -r["grams"])

    return {"window_days": int(days), "categories": categories,
            "top_wasted_foods": foods[:10], "reasons": reasons}


def record_resolution(conn: sqlite3.Connection, user_id: int, item: sqlite3.Row,
                      status: str, grams: float, waste_reason: str = "",
                      risk: float | None = None, kn: Knowledge | None = None,
                      when: str | None = None) -> dict:
    """Write the event row for a consumed/wasted/donated item and return its impact."""
    kn = kn or get_knowledge()
    food = kn.food(item["food_id"])
    kg = max(0.0, float(grams)) / 1000.0
    impact = {
        "grams": round(float(grams), 1),
        "co2e_kg": round(kg * (food.co2e_kg_per_kg if food else 0.0), 4),
        "water_l": round(kg * (food.water_l_per_kg if food else 0.0), 1),
        "value_inr": round(kg * (food.price_inr_per_kg if food else 0.0), 2),
    }
    events_repo.create(
        conn, user_id, item_id=int(item["id"]), food_id=item["food_id"],
        category=item["category"], event_type=status, grams=impact["grams"],
        waste_reason=waste_reason, co2e_kg=impact["co2e_kg"], water_l=impact["water_l"],
        value_inr=impact["value_inr"], risk_at_resolve=risk, occurred_at=when,
    )
    return impact
