"""Habit insights derived from a household's own resolved history.

These are deliberately rule-based rather than learned. There are two reasons.
First, the volume of data one household produces is far too small to fit a
second model on without overfitting. Second, an insight has to be auditable: the
user should be able to see the three items that produced the claim. Every
insight therefore carries an `evidence` block and a projection method that is
stated in the payload rather than hidden.

Projections scale the observed window to 30 days (observed * 30 / window_days)
and are labelled as estimates. They are not promises.
"""
from __future__ import annotations

import datetime as dt
import sqlite3
from collections import defaultdict

from ..knowledge import (Knowledge, category_label,
                          category_title, get_knowledge)
from ..repositories import events as events_repo
from ..repositories import items as items_repo
from . import risk_service

MIN_RESOLVED_FOR_CATEGORY = 3
MIN_REPEATS = 2


def _monthly(value: float, window_days: int) -> float:
    return value * 30.0 / max(1.0, float(window_days))


def _date(v) -> dt.date | None:
    try:
        return dt.date.fromisoformat(str(v)[:10])
    except Exception:
        return None


def generate(conn: sqlite3.Connection, user_id: int, window_days: int = 90,
             kn: Knowledge | None = None) -> dict:
    kn = kn or get_knowledge()
    start = (dt.date.today() - dt.timedelta(days=window_days - 1)).isoformat()
    evs = events_repo.since(conn, user_id, start, ("consumed", "wasted", "donated"))
    history = items_repo.food_history(conn, user_id)

    insights: list[dict] = []

    # ---------------------------------------------------------- category hotspot
    cat: dict[str, dict] = defaultdict(
        lambda: {"w_g": 0.0, "t_g": 0.0, "w_n": 0, "t_n": 0, "co2e": 0.0, "inr": 0.0})
    food: dict[str, dict] = defaultdict(
        lambda: {"w_g": 0.0, "w_n": 0, "co2e": 0.0, "inr": 0.0, "t_n": 0})
    reasons: dict[str, float] = defaultdict(float)
    reason_cost: dict[str, dict] = defaultdict(lambda: {"inr": 0.0, "co2e": 0.0})
    total_w_g = total_g = 0.0

    for e in evs:
        c = cat[e["category"] or "unknown"]
        f = food[e["food_id"]]
        g = float(e["grams"])
        c["t_g"] += g
        c["t_n"] += 1
        f["t_n"] += 1
        total_g += g
        if e["event_type"] == "wasted":
            c["w_g"] += g
            c["w_n"] += 1
            c["co2e"] += float(e["co2e_kg"])
            c["inr"] += float(e["value_inr"])
            f["w_g"] += g
            f["w_n"] += 1
            f["co2e"] += float(e["co2e_kg"])
            f["inr"] += float(e["value_inr"])
            rk = e["waste_reason"] or "unspecified"
            reasons[rk] += g
            reason_cost[rk]["inr"] += float(e["value_inr"])
            reason_cost[rk]["co2e"] += float(e["co2e_kg"])
            total_w_g += g

    ranked = sorted(
        ((k, v) for k, v in cat.items() if v["t_n"] >= MIN_RESOLVED_FOR_CATEGORY
         and v["w_g"] > 0),
        key=lambda kv: -kv[1]["w_g"],
    )
    if ranked:
        name, v = ranked[0]
        rate = v["w_g"] / v["t_g"] if v["t_g"] else 0.0
        insights.append({
            "id": "category_hotspot",
            "type": "hotspot",
            "severity": 3 if rate > 0.3 else 2,
            "title": "%s is your biggest source of waste" % category_title(name),
            "detail": ("You threw away %.1f kg of %s in the last %d days - %d%% of all "
                       "the %s you handled. Buying it in smaller amounts, more often, is "
                       "the single highest-leverage change available to you."
                       % (v["w_g"] / 1000.0, category_label(name), window_days,
                          round(rate * 100), category_label(name))),
            "action": ("Halve the pack size for %s on your next shop"
                       % category_label(name)),
            "monthly_inr": round(_monthly(v["inr"], window_days), 2),
            "monthly_co2e_kg": round(_monthly(v["co2e"], window_days), 3),
            "evidence": {"category": name, "wasted_kg": round(v["w_g"] / 1000.0, 3),
                         "waste_rate": round(rate, 4), "items": v["w_n"],
                         "window_days": window_days},
        })

    # ------------------------------------------------------------- repeat offenders
    repeats = sorted((kv for kv in food.items() if kv[1]["w_n"] >= MIN_REPEATS),
                     key=lambda kv: -kv[1]["co2e"])
    if repeats:
        fid, v = repeats[0]
        f = kn.food(fid)
        label = f.name if f else fid
        insights.append({
            "id": "repeat_offender_%s" % fid,
            "type": "repeat",
            "severity": 3 if v["w_n"] >= 4 else 2,
            "title": "%s has gone off %d times" % (label, v["w_n"]),
            "detail": ("%d separate times in %d days, totalling %.0f g and %.2f kg CO2e. "
                       "This is a pattern rather than bad luck, so treat it as a shopping "
                       "or storage problem instead of a memory problem."
                       % (v["w_n"], window_days, v["w_g"], v["co2e"])),
            "action": ("Buy %s only when you have a specific dish planned for it" % label),
            "monthly_inr": round(_monthly(v["inr"], window_days), 2),
            "monthly_co2e_kg": round(_monthly(v["co2e"], window_days), 3),
            "evidence": {"food_id": fid, "times": v["w_n"],
                         "wasted_grams": round(v["w_g"], 1),
                         "waste_share_of_handled": round(v["w_n"] / max(1, v["t_n"]), 3)},
        })

    # ----------------------------------------------------------------- storage fix
    storage_loss: dict[str, dict] = defaultdict(
        lambda: {"n": 0, "grams": 0.0, "from": "", "to": "", "gain": 0.0})
    for it in history:
        if it["status"] != "wasted":
            continue
        f = kn.food(it["food_id"])
        if f is None:
            continue
        used, best = it["storage"], f.recommended_storage
        if used == best:
            continue
        gain = f.recommended_shelf_days - max(1.0, f.shelf_days(used))
        if gain < 2:
            continue
        d = storage_loss[it["food_id"]]
        d["n"] += 1
        d["grams"] += float(it["grams_remaining"] or 0.0)
        d["from"], d["to"], d["gain"] = used, best, gain
    if storage_loss:
        fid, d = max(storage_loss.items(), key=lambda kv: (kv[1]["n"], kv[1]["gain"]))
        f = kn.food(fid)
        insights.append({
            "id": "storage_fix_%s" % fid,
            "type": "storage",
            "severity": 2,
            "title": "Move your %s to the %s" % (f.name.lower(), d["to"]),
            "detail": ("You lost %s from the %s %d time%s. In the %s it keeps for about "
                       "%d days instead of %d - a %d day head start for no effort."
                       % (f.name.lower(), d["from"], d["n"], "" if d["n"] == 1 else "s",
                          d["to"], int(f.recommended_shelf_days),
                          int(max(1, f.shelf_days(d["from"]))), int(d["gain"]))),
            "action": "Store %s in the %s from now on" % (f.name.lower(), d["to"]),
            "monthly_inr": round(_monthly(d["grams"] / 1000.0 * f.price_inr_per_kg,
                                          window_days), 2),
            "monthly_co2e_kg": round(_monthly(d["grams"] / 1000.0 * f.co2e_kg_per_kg,
                                              window_days), 3),
            "evidence": {"food_id": fid, "occasions": d["n"], "stored_in": d["from"],
                         "should_be": d["to"], "extra_days": int(d["gain"])},
        })

    # -------------------------------------------------------------------- timing
    lags = [
        (_date(it["resolved_at"]) - _date(it["purchase_date"])).days
        for it in history
        if it["status"] == "wasted" and _date(it["resolved_at"]) and _date(it["purchase_date"])
    ]
    if len(lags) >= 3:
        avg = sum(lags) / len(lags)
        insights.append({
            "id": "timing_window",
            "type": "timing",
            "severity": 1,
            "title": "Food tends to be lost around day %d" % round(avg),
            "detail": ("Across %d losses, the average gap between buying and binning was "
                       "%.1f days. A single check of the Eat Me First list on day %d of "
                       "your shopping cycle would catch most of it."
                       % (len(lags), avg, max(1, round(avg) - 1))),
            "action": "Set a reminder to open FridgeSense every %d days" % max(2, round(avg) - 1),
            "monthly_inr": None,
            "monthly_co2e_kg": None,
            "evidence": {"losses": len(lags), "mean_days_to_waste": round(avg, 1),
                         "min": min(lags), "max": max(lags)},
        })

    # ------------------------------------------------------------- dominant reason
    if reasons:
        top_reason, grams = max(reasons.items(), key=lambda kv: kv[1])
        share = grams / total_w_g if total_w_g else 0.0
        reason_inr = reason_cost[top_reason]["inr"]
        reason_co2e = reason_cost[top_reason]["co2e"]
        catalogue = {
            "forgot_about_it": ("Most of your waste is simply forgotten food",
                                "Put the four riskiest items on the front shelf at eye level"),
            "cooked_too_much": ("You are cooking more than the household eats",
                                "Cook for one fewer portion and use the meal planner's serving count"),
            "stored_wrong": ("Storage choices are costing you shelf life",
                             "Follow the storage suggestion on each item card"),
            "bought_too_much": ("The problem starts at the shop, not the fridge",
                                "Shop twice a week for fresh items instead of once"),
            "went_off_early": ("Items are failing before their expected date",
                               "Buy fresh produce later in the week and check it on arrival"),
            "leftovers_ignored": ("Leftovers are not making it back to the table",
                                  "Plan one 'leftovers night' per week"),
            "poor_planning": ("Meals are being decided too late",
                              "Use the three-day plan on the Recipes page"),
            "expired_unopened": ("Sealed items are expiring untouched",
                                 "Move long-life items to the front when you unpack"),
        }
        title, action = catalogue.get(
            top_reason, ("Your waste has one dominant cause", "Review the reason breakdown"))
        insights.append({
            "id": "dominant_reason",
            "type": "behaviour",
            "severity": 2,
            "title": title,
            "detail": ("'%s' accounts for %d%% of everything you have thrown away "
                       "(%.1f kg). Fixing one cause is easier than fixing all of them."
                       % (top_reason.replace("_", " "), round(share * 100), grams / 1000.0)),
            "action": action,
            "monthly_inr": round(_monthly(reason_inr, window_days), 2),
            "monthly_co2e_kg": round(_monthly(reason_co2e, window_days), 3),
            "evidence": {"reason": top_reason, "share": round(share, 4),
                         "grams": round(grams, 1)},
        })

    # ------------------------------------------------------------- pantry right now
    scored = risk_service.score_pantry(conn, user_id, kn)
    urgent = [s for s in scored if s["risk"] >= 0.7]
    if urgent:
        loss = sum(s["at_risk_value_inr"] for s in urgent)
        co2e = sum(s["at_risk_co2e_kg"] for s in urgent)
        insights.append({
            "id": "urgent_now",
            "type": "urgent",
            "severity": 3,
            "title": "%d item%s need cooking in the next day or two" % (
                len(urgent), "" if len(urgent) == 1 else "s"),
            "detail": ("%s are all rated critical. On current form that is about Rs %.0f "
                       "and %.2f kg CO2e hanging in the balance."
                       % (", ".join(s["name"] for s in urgent[:4]), loss, co2e)),
            "action": "Open the meal planner and build a two-day plan around them",
            "monthly_inr": round(loss, 2),
            "monthly_co2e_kg": round(co2e, 3),
            "evidence": {"items": [{"name": s["name"], "risk": s["risk"],
                                    "days_to_expiry": s["days_to_expiry"]} for s in urgent[:6]]},
        })

    # ------------------------------------------------------------------------ win
    best = sorted(
        ((k, v) for k, v in cat.items() if v["t_n"] >= MIN_RESOLVED_FOR_CATEGORY),
        key=lambda kv: kv[1]["w_g"] / max(1.0, kv[1]["t_g"]),
    )
    if best:
        name, v = best[0]
        rate = v["w_g"] / v["t_g"] if v["t_g"] else 0.0
        if rate < 0.1:
            insights.append({
                "id": "win_category",
                "type": "win",
                "severity": 0,
                "title": "Your %s habits are excellent" % category_label(name),
                "detail": ("%s of the %s you bought was wasted, against a %d%% global "
                           "household average. Whatever you are doing there, it is worth "
                           "copying across to the rest of the kitchen."
                           % ("None" if round(rate * 100) == 0
                              else "Only %d%%" % round(rate * 100),
                              category_label(name), 22)),
                "action": "Keep it up",
                "monthly_inr": None,
                "monthly_co2e_kg": None,
                "evidence": {"category": name, "waste_rate": round(rate, 4),
                             "items": v["t_n"]},
            })

    # None means "no cost can honestly be attributed to this one", which is not
    # the same as zero, so it is kept as None for the client and only coerced here
    # to keep the ordering total.
    insights.sort(key=lambda i: (-i["severity"], -(i["monthly_inr"] or 0.0)))
    return {
        "window_days": window_days,
        "insights": insights,
        "projection_method": ("Monthly figures scale the observed window linearly to 30 "
                              "days and are estimates, not guarantees."),
        # Each insight is a different lens on one set of losses: the same wasted
        # spinach can appear under a category, a cause and a timing pattern. The
        # figures therefore overlap and must never be added together, which a
        # dashboard would otherwise be tempted to do.
        "figures_overlap": True,
        "overlap_note": ("Insights are different views of the same losses, so their "
                         "monthly figures overlap and should not be summed. The total "
                         "actually at stake is on the impact summary."),
        "data_sufficiency": {
            "resolved_events": len(evs),
            "wasted_events": sum(1 for e in evs if e["event_type"] == "wasted"),
            "enough_for_confidence": len(evs) >= 15,
            "note": ("Fewer than 15 resolved items means these patterns are indicative "
                     "only." if len(evs) < 15 else "Sample size is adequate for trends."),
        },
    }
