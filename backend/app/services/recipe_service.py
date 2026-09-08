"""Recipe retrieval that is biased towards rescuing food, not just matching it.

A plain cosine similarity over ingredient sets answers "what can I cook?". That
is the wrong question here. The right question is "what can I cook that uses up
the things about to go off?", so the pantry vector is weighted by each item's
spoilage risk before retrieval, and the ranking blends four terms:

  similarity   TF-IDF cosine between the risk-weighted pantry and the recipe
  coverage     fraction of the recipe's required ingredients actually in stock
  rescue       share of the recipe's required mass that comes from at-risk items
  penalty      a small discount per missing required ingredient

Rare ingredients carry more weight than common ones because the vectoriser is
IDF-weighted, so a recipe that uses up the coriander scores above one that only
matches on onions.
"""
from __future__ import annotations

import sqlite3

import numpy as np

from ..knowledge import Knowledge, get_knowledge
from ..ml.tfidf import cosine_similarity
from . import risk_service

RISK_WEIGHT_GAIN = 2.5      # pantry token weight = 1 + gain * risk
AT_RISK_THRESHOLD = 0.45
W_SIM, W_COVER, W_RESCUE = 0.40, 0.35, 0.25
MISSING_PENALTY = 0.07
MIN_MULTIPLIER = 0.35


def _availability(scored: list[dict]) -> dict[str, dict]:
    """Collapse the pantry to one entry per food id, keeping the worst risk."""
    avail: dict[str, dict] = {}
    for s in scored:
        a = avail.setdefault(s["food_id"], {
            "grams": 0.0, "risk": 0.0, "name": s["name"], "item_ids": [],
            "days_to_expiry": s["days_to_expiry"],
        })
        a["grams"] += s["grams_remaining"]
        a["risk"] = max(a["risk"], s["risk"])
        a["item_ids"].append(s["item_id"])
        a["days_to_expiry"] = min(a["days_to_expiry"], s["days_to_expiry"])
    return avail


def _score_recipe(recipe: dict, avail: dict[str, dict], kn: Knowledge,
                  sim: float) -> dict | None:
    required = [i for i in recipe["ingredients"] if not i.get("optional")]
    optional = [i for i in recipe["ingredients"] if i.get("optional")]
    if not required:
        return None

    req_mass = sum(i["grams"] for i in required) or 1.0
    have_mass = 0.0
    rescue_mass = 0.0
    uses, missing, extras = [], [], []
    rescue_co2e = rescue_water = rescue_value = 0.0

    for ing in required + optional:
        food = kn.food(ing["id"])
        label = food.name if food else ing["id"]
        a = avail.get(ing["id"])
        if a is None:
            (missing if not ing.get("optional") else extras).append(
                {"food_id": ing["id"], "name": label, "grams": ing["grams"]})
            continue
        used = min(float(ing["grams"]), a["grams"])
        at_risk = a["risk"] >= AT_RISK_THRESHOLD
        if not ing.get("optional"):
            have_mass += used
            if at_risk:
                rescue_mass += used
        if at_risk and food is not None:
            kg = used / 1000.0
            rescue_co2e += kg * food.co2e_kg_per_kg
            rescue_water += kg * food.water_l_per_kg
            rescue_value += kg * food.price_inr_per_kg
        uses.append({
            "food_id": ing["id"], "name": label,
            "grams_needed": round(float(ing["grams"]), 1),
            "grams_available": round(a["grams"], 1),
            "grams_used": round(used, 1),
            "risk": round(a["risk"], 3),
            "at_risk": at_risk,
            "optional": bool(ing.get("optional")),
            "short_by": round(max(0.0, float(ing["grams"]) - a["grams"]), 1),
        })

    coverage = have_mass / req_mass
    rescue_share = rescue_mass / req_mass
    raw = W_SIM * sim + W_COVER * coverage + W_RESCUE * rescue_share
    multiplier = max(MIN_MULTIPLIER, 1.0 - MISSING_PENALTY * len(missing))
    score = raw * multiplier

    return {
        "recipe_id": recipe["id"],
        "title": recipe["title"],
        "cuisine": recipe["cuisine"],
        "meal": recipe["meal"],
        "diet": recipe["diet"],
        "minutes": recipe["minutes"],
        "servings": recipe["servings"],
        "steps": recipe["steps"],
        "rescue_note": recipe.get("rescue_note", ""),
        "score": round(float(score), 4),
        "similarity": round(float(sim), 4),
        "coverage": round(float(coverage), 3),
        "rescue_share": round(float(rescue_share), 3),
        "missing_count": len(missing),
        "missing": missing,
        "optional_missing": extras,
        "uses": sorted(uses, key=lambda u: (-u["risk"], u["optional"])),
        "rescues": [u["name"] for u in uses if u["at_risk"] and not u["optional"]],
        "rescue_grams": round(rescue_mass, 1),
        "rescue_co2e_kg": round(rescue_co2e, 4),
        "rescue_water_l": round(rescue_water, 1),
        "rescue_value_inr": round(rescue_value, 2),
    }


def rank_recipes(scored: list[dict], kn: Knowledge | None = None, limit: int = 12,
                 meal: str | None = None, diet: str | None = None,
                 max_minutes: int | None = None,
                 require_rescue: bool = False) -> list[dict]:
    kn = kn or get_knowledge()
    if not scored:
        return []
    avail = _availability(scored)

    weights = {fid: 1.0 + RISK_WEIGHT_GAIN * a["risk"] for fid, a in avail.items()}
    qvec = kn.recipe_vec.transform([list(avail.keys())], weights=[weights])[0]
    sims = cosine_similarity(qvec, kn.recipe_matrix)[0]

    out = []
    for idx, recipe in enumerate(kn.recipes):
        if meal and meal != "any" and recipe["meal"] != meal:
            continue
        if diet and diet != "any":
            if diet == "vegetarian" and recipe["diet"] not in ("vegetarian", "vegan"):
                continue
            if diet == "vegan" and recipe["diet"] != "vegan":
                continue
        if max_minutes and recipe["minutes"] > max_minutes:
            continue
        card = _score_recipe(recipe, avail, kn, float(sims[idx]))
        if card is None:
            continue
        if require_rescue and card["rescue_grams"] <= 0:
            continue
        out.append(card)

    out.sort(key=lambda c: (-c["score"], c["missing_count"], c["minutes"]))
    return out[:limit]


def suggest(conn: sqlite3.Connection, user_id: int, kn: Knowledge | None = None,
            **kwargs) -> dict:
    kn = kn or get_knowledge()
    scored = risk_service.score_pantry(conn, user_id, kn)
    cards = rank_recipes(scored, kn, **kwargs)
    at_risk = [s for s in scored if s["risk"] >= AT_RISK_THRESHOLD]
    return {
        "recipes": cards,
        "at_risk_items": [
            {"item_id": s["item_id"], "name": s["name"], "risk": s["risk"],
             "grams_remaining": s["grams_remaining"], "days_to_expiry": s["days_to_expiry"]}
            for s in at_risk
        ],
        "covered_at_risk": sorted({
            u["food_id"] for c in cards for u in c["uses"]
            if u["at_risk"] and not u["optional"]
        }),
    }


def meal_plan(conn: sqlite3.Connection, user_id: int, days: int = 3,
              kn: Knowledge | None = None) -> dict:
    """Greedy plan: repeatedly take the dish that rescues the most at-risk mass,
    deducting what it consumes so the next pick cannot spend the same spinach twice.
    """
    kn = kn or get_knowledge()
    scored = risk_service.score_pantry(conn, user_id, kn)
    avail = _availability(scored)
    remaining = {fid: dict(a) for fid, a in avail.items()}
    slots = ["lunch", "dinner"]
    plan, used_recipes = [], set()

    for day in range(1, max(1, min(int(days), 7)) + 1):
        for slot in slots:
            best, best_key = None, None
            weights = {fid: 1.0 + RISK_WEIGHT_GAIN * a["risk"]
                       for fid, a in remaining.items() if a["grams"] > 0}
            if not weights:
                break
            live = {fid: a for fid, a in remaining.items() if a["grams"] > 0}
            qvec = kn.recipe_vec.transform([list(live.keys())], weights=[weights])[0]
            sims = cosine_similarity(qvec, kn.recipe_matrix)[0]
            for idx, recipe in enumerate(kn.recipes):
                if recipe["id"] in used_recipes:
                    continue
                if recipe["meal"] not in (slot, "any", "snack"):
                    if not (slot == "lunch" and recipe["meal"] == "breakfast"):
                        continue
                card = _score_recipe(recipe, live, kn, float(sims[idx]))
                if card is None or card["rescue_grams"] <= 0:
                    continue
                key = (card["rescue_grams"], card["score"])
                if best_key is None or key > best_key:
                    best, best_key = card, key
            if best is None:
                continue
            for u in best["uses"]:
                if u["food_id"] in remaining:
                    remaining[u["food_id"]]["grams"] = max(
                        0.0, remaining[u["food_id"]]["grams"] - u["grams_used"])
            used_recipes.add(best["recipe_id"])
            plan.append({"day": day, "slot": slot, **best})

    total_grams = sum(p["rescue_grams"] for p in plan)
    return {
        "days": days,
        "plan": plan,
        "totals": {
            "recipes": len(plan),
            "rescue_grams": round(total_grams, 1),
            "rescue_co2e_kg": round(sum(p["rescue_co2e_kg"] for p in plan), 3),
            "rescue_water_l": round(sum(p["rescue_water_l"] for p in plan), 1),
            "rescue_value_inr": round(sum(p["rescue_value_inr"] for p in plan), 2),
        },
        "unrescued": [
            {"name": a["name"], "grams": round(a["grams"], 1), "risk": round(a["risk"], 3)}
            for fid, a in remaining.items()
            if a["grams"] > 1.0 and avail[fid]["risk"] >= AT_RISK_THRESHOLD
        ],
    }
