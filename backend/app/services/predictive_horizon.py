"""Predictive Horizon Engine for Indian Kitchen Bulk Staples.

Vegetables like cauliflower, cabbage, spinach, and paneer are discrete meal items
consumed in 1-2 cooking sessions. Conversely, bulk base ingredients like onions,
tomatoes, potatoes, ginger, garlic, and chillies are bought in multi-kilogram batches
and depleted daily across breakfast, lunch, and dinner.

This module implements the Zero-Effort Predictive Horizon:
1. Classifies bulk staples vs discrete single-cooking produce.
2. Derives household burn rates based on dietary baseline (ICMR) * household_size.
3. Automatically computes current stock pace without requiring daily manual logs.
4. Generates horizon indicators, run-out alerts, and 1-tap calibration hooks.
"""
from __future__ import annotations

import datetime as dt
import sqlite3

BULK_STAPLE_CONFIG = {
    "onion": {
        "name_hi": "Pyaz",
        "icon": "🧅",
        "category": "base_vegetable",
        "default_daily_g": 60.0,
        "portion_desc": "Used daily for tadka and gravies",
    },
    "potato": {
        "name_hi": "Aloo",
        "icon": "🥔",
        "category": "base_vegetable",
        "default_daily_g": 100.0,
        "portion_desc": "Used across dry sabzis, parathas, and curries",
    },
    "tomato": {
        "name_hi": "Tamatar",
        "icon": "🍅",
        "category": "base_vegetable",
        "default_daily_g": 80.0,
        "portion_desc": "Used daily for dal tadka and curry bases",
    },
    "garlic": {
        "name_hi": "Lehsun",
        "icon": "🧄",
        "category": "aromatic",
        "default_daily_g": 8.0,
        "portion_desc": "Daily paste and seasoning",
    },
    "ginger": {
        "name_hi": "Adrak",
        "icon": "🫚",
        "category": "aromatic",
        "default_daily_g": 10.0,
        "portion_desc": "Daily chai and cooking aromatics",
    },
    "green_chilli": {
        "name_hi": "Hari Mirch",
        "icon": "🌶️",
        "category": "aromatic",
        "default_daily_g": 10.0,
        "portion_desc": "Daily tempering and seasoning",
    },
    "atta": {
        "name_hi": "Atta",
        "icon": "🌾",
        "category": "grain",
        "default_daily_g": 120.0,
        "portion_desc": "Daily roti and paratha staple",
    },
    "rice": {
        "name_hi": "Chawal",
        "icon": "🍚",
        "category": "grain",
        "default_daily_g": 120.0,
        "portion_desc": "Daily cooked rice and khichdi",
    },
    "cooking_oil": {
        "name_hi": "Tel",
        "icon": "🫗",
        "category": "oil",
        "default_daily_g": 30.0,
        "portion_desc": "Daily cooking medium",
    },
    "mustard_oil": {
        "name_hi": "Sarson Tel",
        "icon": "🫗",
        "category": "oil",
        "default_daily_g": 25.0,
        "portion_desc": "Daily cooking medium",
    },
    "ghee": {
        "name_hi": "Ghee",
        "icon": "🧈",
        "category": "dairy_fat",
        "default_daily_g": 15.0,
        "portion_desc": "Daily roti greasing and tadka",
    },
}


def is_bulk_staple(food_id: str, category: str = "", grams_initial: float = 0.0) -> bool:
    """Identifies whether an item behaves as a continuous multi-day staple."""
    fid = str(food_id).lower()
    if fid in BULK_STAPLE_CONFIG:
        return True
    cat = str(category).lower()
    if cat in ("grains", "oils") and fid not in ("bread", "bun", "pav") and grams_initial >= 300:
        return True
    return False


def compute_predictive_horizon(row: dict | sqlite3.Row, food, ctx: dict, today: dt.date | None = None) -> dict | None:
    """Calculates zero-effort predictive burn rate and horizon projection for bulk staples."""
    food_id = str(getattr(food, "id", "") or row.get("food_id", "")).lower()
    category = str(getattr(food, "category", "") or row.get("category", "")).lower()
    grams_init = float(row["grams_initial"] if "grams_initial" in row.keys() else row["grams_remaining"])

    if not is_bulk_staple(food_id, category, grams_init):
        return None

    today = today or dt.date.today()
    config = BULK_STAPLE_CONFIG.get(food_id, {
        "name_hi": food.name,
        "icon": "🧺",
        "category": "staple",
        "default_daily_g": 50.0,
        "portion_desc": "Daily household staple",
    })

    # 1. Household burn rate calculation
    hh_size = max(1.0, float(ctx.get("household_size", 3)))
    daily_g_person = float(getattr(food, "daily_g_per_person", None) or config["default_daily_g"])
    daily_burn_g = max(5.0, round(daily_g_person * hh_size, 1))

    # 2. Elapsed time
    try:
        raw_p = str(row["purchase_date"])[:10]
        purchase_date = dt.date.fromisoformat(raw_p)
    except (ValueError, KeyError, TypeError):
        purchase_date = today

    days_elapsed = max(0.0, float((today - purchase_date).days))

    # 3. Projected stock burn curve
    projected_consumed_g = min(grams_init, round(days_elapsed * daily_burn_g, 1))
    projected_remaining_g = max(0.0, round(grams_init - projected_consumed_g, 1))

    # Existing database grams_remaining
    stored_remaining_g = max(0.0, float(row["grams_remaining"]))

    # Effective remaining: respect recipe deductions and auto-burn pace
    effective_remaining_g = min(stored_remaining_g, projected_remaining_g)

    # 4. Days of stock remaining & total capacity
    total_stock_days = max(1.0, round(grams_init / daily_burn_g, 1))
    days_remaining = max(0.0, round(effective_remaining_g / daily_burn_g, 1))
    percent_remaining = max(0, min(100, int(round((effective_remaining_g / max(1.0, grams_init)) * 100))))

    empty_date = purchase_date + dt.timedelta(days=int(total_stock_days))
    projected_empty_date = empty_date.isoformat()

    # 5. Status tier and user-friendly labels
    if days_remaining > 4.0:
        status_tier = "good"
        status_label = f"Well-stocked (~{days_remaining:.1f}d left)"
    elif days_remaining > 1.5:
        status_tier = "steady"
        status_label = f"Running steadily (~{days_remaining:.1f}d left)"
    elif days_remaining > 0.4:
        status_tier = "low"
        status_label = f"Running low (~{days_remaining:.1f}d left)"
    else:
        status_tier = "critical"
        status_label = "Due to run out today"

    is_near_empty = days_remaining <= 1.5
    is_overdue = days_elapsed >= total_stock_days and effective_remaining_g <= (daily_burn_g * 0.5)

    return {
        "is_bulk_staple": True,
        "food_id": food_id,
        "name_hi": config["name_hi"],
        "icon": config["icon"],
        "portion_desc": config["portion_desc"],
        "household_size": int(hh_size),
        "daily_burn_g": daily_burn_g,
        "grams_initial": round(grams_init, 1),
        "projected_consumed_g": round(projected_consumed_g, 1),
        "effective_remaining_g": round(effective_remaining_g, 1),
        "days_elapsed": int(days_elapsed),
        "total_stock_days": total_stock_days,
        "days_remaining": days_remaining,
        "percent_remaining": percent_remaining,
        "projected_empty_date": projected_empty_date,
        "status_tier": status_tier,
        "status_label": status_label,
        "is_near_empty": is_near_empty,
        "is_overdue": is_overdue,
        "checkin_prompt": {
            "title": f"{food.name} ({config['name_hi']}) is running low",
            "message": (
                f"Bought {int(days_elapsed)} days ago. Based on your household of {int(hh_size)} "
                f"(~{int(daily_burn_g)}g/day), ~{int(effective_remaining_g)}g is left."
            ),
        },
    }
