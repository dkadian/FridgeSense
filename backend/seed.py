"""Create a demo household with enough history to exercise every screen.

Run directly:  python3 backend/seed.py [--reset]

The simulation is deliberately opinionated rather than uniformly random. The demo
household has a leafy-greens problem, keeps bread in the fridge where it stales
early, over-buys milk, and is disciplined about grains and pulses. Those planted
patterns are what the insights engine should independently rediscover, which
makes the seed double as a sanity check on it.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import db                                        # noqa: E402
from app.knowledge import get_knowledge                   # noqa: E402
from app.repositories import events as events_repo        # noqa: E402
from app.repositories import items as items_repo          # noqa: E402
from app.repositories import users as users_repo          # noqa: E402
from app.security import hash_password                    # noqa: E402
from app.services import risk_service                     # noqa: E402

DEMO_EMAIL = "demo@fridgesense.app"
DEMO_PASSWORD = "demo1234"
DEMO_NAME = "Demo Household"
HOUSEHOLD_SIZE = 4
HISTORY_DAYS = 84

# The weekly shop. (food_id, grams, times per week)
WEEKLY_BASKET = [
    ("spinach", 400, 2), ("methi", 250, 1), ("coriander", 100, 2),
    ("tomato", 1000, 1), ("onion", 1500, 1), ("potato", 1500, 1),
    ("okra", 400, 1), ("cauliflower", 700, 1), ("carrot", 500, 1),
    ("capsicum", 300, 1), ("cucumber", 500, 1), ("green_chilli", 100, 1),
    ("milk", 2060, 3), ("curd", 400, 2), ("paneer", 200, 1),
    ("eggs", 600, 1), ("bread", 400, 2), ("banana", 1200, 1),
    ("apple", 800, 1), ("orange", 1000, 1),
    ("rice", 5000, 0.25), ("atta", 5000, 0.25), ("toor_dal", 1000, 0.5),
    ("chana_dal", 500, 0.5), ("cooking_oil", 1000, 0.25), ("sugar", 1000, 0.2),
    ("chicken", 500, 0.5), ("poha", 500, 0.3), ("cooked_rice", 500, 2),
    ("cooked_dal", 600, 1.5), ("cooked_curry", 500, 1),
]

# Planted habits. Waste probability per category, and the storage mistakes.
CATEGORY_WASTE = {
    "leafy_greens": 0.46, "herbs": 0.52, "vegetables": 0.20, "fruits": 0.19,
    "dairy": 0.14, "cooked_leftovers": 0.30, "bakery": 0.26, "meat_fish": 0.10,
    "grains": 0.02, "pulses": 0.02, "oils": 0.01, "spices": 0.01,
    "condiments": 0.02, "sweeteners": 0.01, "beverages": 0.05, "frozen": 0.03,
}
STORAGE_MISTAKES = {"bread": "fridge", "banana": "fridge", "onion": "fridge"}
REASONS = {
    "leafy_greens": ["forgot_about_it", "forgot_about_it", "bought_too_much"],
    "herbs": ["forgot_about_it", "went_off_early"],
    "cooked_leftovers": ["leftovers_ignored", "cooked_too_much"],
    "bakery": ["stored_wrong", "went_off_early"],
    "dairy": ["bought_too_much", "forgot_about_it"],
}
DEFAULT_REASONS = ["forgot_about_it", "poor_planning", "bought_too_much"]

# History is generated up to this many days before today; everything closer is
# supplied by CURRENT_PANTRY instead. Without that split, long-life staples
# accumulate one live row per purchase and the pantry fills with duplicate rice.
HISTORY_CUTOFF_DAYS = 8

# The pantry as it stands today: (food_id, grams, storage, days_since_purchase,
# opened). Curated rather than sampled so the demo reliably shows every risk
# band, both storage mistakes and a believable basket size.
CURRENT_PANTRY = [
    # staples, comfortably safe
    ("rice", 4200, "pantry", 26, 1),
    ("atta", 3500, "pantry", 19, 1),
    ("toor_dal", 800, "pantry", 33, 1),
    ("chana_dal", 450, "pantry", 40, 1),
    ("cooking_oil", 700, "pantry", 26, 1),
    ("sugar", 800, "pantry", 47, 1),
    ("tea", 180, "pantry", 40, 1),
    # midweek vegetables, mostly fine
    ("onion", 1100, "pantry", 6, 1),
    ("potato", 1200, "pantry", 6, 1),
    ("carrot", 400, "fridge", 5, 1),
    ("capsicum", 250, "fridge", 5, 1),
    ("cucumber", 400, "fridge", 4, 0),
    ("cauliflower", 500, "fridge", 5, 0),
    ("apple", 600, "fridge", 5, 0),
    ("orange", 700, "fridge", 5, 0),
    ("eggs", 450, "fridge", 4, 1),
    ("curd", 300, "fridge", 3, 1),
    # the planted storage mistakes
    ("bread", 280, "fridge", 4, 1),
    ("banana", 700, "fridge", 4, 0),
    # about to go off
    ("spinach", 350, "fridge", 4, 1),
    ("coriander", 90, "fridge", 5, 1),
    ("methi", 200, "fridge", 4, 1),
    ("tomato", 600, "pantry", 5, 1),
    ("paneer", 200, "fridge", 3, 1),
    ("milk", 1030, "fridge", 2, 1),
    ("cooked_rice", 450, "fridge", 1, 1),
    ("cooked_dal", 500, "fridge", 2, 1),
]


def _iso(day: dt.date, hour: int = 19) -> str:
    return dt.datetime.combine(day, dt.time(hour, 0)).isoformat() + "+00:00"


def seed_demo(conn, seed: int = 20260825, today: dt.date | None = None) -> dict:
    """Wipe and rebuild the demo user. Returns a small report."""
    kn = get_knowledge()
    rng = random.Random(seed)
    today = today or dt.date.today()

    existing = users_repo.by_email(conn, DEMO_EMAIL)
    if existing is not None:
        conn.execute("DELETE FROM events WHERE user_id = ?", (int(existing["id"]),))
        conn.execute("DELETE FROM pantry_items WHERE user_id = ?", (int(existing["id"]),))
        conn.execute("DELETE FROM users WHERE id = ?", (int(existing["id"]),))

    user_id = users_repo.create(conn, DEMO_EMAIL, DEMO_NAME,
                                hash_password(DEMO_PASSWORD), HOUSEHOLD_SIZE)

    resolved = wasted = 0
    start = today - dt.timedelta(days=HISTORY_DAYS)

    for offset in range(HISTORY_DAYS + 1):
        day = start + dt.timedelta(days=offset)
        days_ago = (today - day).days
        if days_ago < HISTORY_CUTOFF_DAYS:
            break                     # recent days are covered by CURRENT_PANTRY
        for food_id, grams, per_week in WEEKLY_BASKET:
            if rng.random() > per_week / 7.0:
                continue
            food = kn.food(food_id)
            if food is None:
                continue

            storage = STORAGE_MISTAKES.get(food_id, food.storage_default)
            if food_id in STORAGE_MISTAKES and rng.random() < 0.35:
                storage = food.storage_default          # they get it right sometimes
            shelf = food.shelf_days(storage)
            if shelf <= 0:
                storage, shelf = food.storage_default, food.shelf_days(food.storage_default)
            qty = grams * rng.choice([0.75, 1.0, 1.0, 1.25])
            expiry = day + dt.timedelta(days=int(max(1, round(shelf))))

            p_waste = CATEGORY_WASTE.get(food.category, 0.12)
            if storage != food.storage_default:
                p_waste = min(0.85, p_waste * 1.7)
            is_waste = rng.random() < p_waste

            # Timing matters for the impact figures. Food that gets eaten is
            # normally eaten with life still on the clock; food that is thrown
            # away typically dies at or just past its date. Drawing both from one
            # uniform lag would mark almost every meal a last-minute "rescue".
            if is_waste:
                lag = int(round(shelf)) + rng.randint(0, 3)
                lost = qty * rng.choice([0.4, 0.6, 1.0, 1.0])
            else:
                lag = max(1, int(round(shelf * rng.uniform(0.25, 0.9))))
                lost = qty
            resolve_day = min(today - dt.timedelta(days=1), day + dt.timedelta(days=lag))
            if resolve_day < day:
                resolve_day = day

            item_id = items_repo.create(
                conn, user_id, food_id=food_id, display_name=food.name,
                category=food.category, grams_initial=qty,
                grams_remaining=0.0, storage=storage,
                opened=1 if rng.random() < 0.6 else 0,
                purchase_date=day.isoformat(), expiry_date=expiry.isoformat(),
                status="wasted" if is_waste else "consumed",
                created_at=_iso(day, 11), resolved_at=_iso(resolve_day),
            )
            events_repo.create(conn, user_id, item_id=item_id, food_id=food_id,
                               category=food.category, event_type="added", grams=qty,
                               occurred_at=_iso(day, 11))

            kg = lost / 1000.0
            # Risk at resolution. Backfilled rather than scored, because the real
            # model needs the pantry state as it was on that day and replaying 84
            # days of it is not worth the cost for demo data.
            #
            # The curve is deliberately convex (exponent 2.2) instead of linear in
            # the fraction of shelf life used. The trained model behaves that way:
            # risk stays flat while an item still has real time left and climbs
            # steeply near the date. A linear stand-in rated more than half of all
            # meals "high risk", which would have inflated the rescued total.
            life_left = (expiry - resolve_day).days
            used = 1.0 - life_left / max(1.0, shelf)
            approx_risk = max(0.02, min(0.99, max(0.0, used) ** 2.2))
            if is_waste:
                approx_risk = max(approx_risk, 0.6)
            pool = REASONS.get(food.category, DEFAULT_REASONS)
            events_repo.create(
                conn, user_id, item_id=item_id, food_id=food_id,
                category=food.category, event_type="wasted" if is_waste else "consumed",
                grams=lost, waste_reason=rng.choice(pool) if is_waste else "",
                co2e_kg=kg * food.co2e_kg_per_kg, water_l=kg * food.water_l_per_kg,
                value_inr=kg * food.price_inr_per_kg,
                risk_at_resolve=round(approx_risk, 4), occurred_at=_iso(resolve_day),
            )
            resolved += 1
            wasted += 1 if is_waste else 0

            if is_waste and lost < qty:          # partial loss: rest was eaten
                eaten = (qty - lost) / 1000.0
                events_repo.create(
                    conn, user_id, item_id=item_id, food_id=food_id,
                    category=food.category, event_type="consumed",
                    grams=qty - lost, co2e_kg=eaten * food.co2e_kg_per_kg,
                    water_l=eaten * food.water_l_per_kg,
                    value_inr=eaten * food.price_inr_per_kg,
                    risk_at_resolve=round(approx_risk, 4), occurred_at=_iso(resolve_day),
                )

    # ------------------------------------------------------------ live pantry
    missing = []
    for food_id, grams, storage, days_ago, opened in CURRENT_PANTRY:
        food = kn.food(food_id)
        if food is None:
            missing.append(food_id)
            continue
        bought = today - dt.timedelta(days=days_ago)
        shelf = food.shelf_days(storage)
        if shelf <= 0:
            storage = food.storage_default
            shelf = food.shelf_days(storage)
        expiry = bought + dt.timedelta(days=int(max(1, round(shelf))))
        items_repo.create(
            conn, user_id, food_id=food_id, display_name=food.name,
            category=food.category, grams_initial=grams, grams_remaining=grams,
            storage=storage, opened=opened, purchase_date=bought.isoformat(),
            expiry_date=expiry.isoformat(), created_at=_iso(bought, 11),
        )
        events_repo.create(conn, user_id, food_id=food_id, category=food.category,
                           event_type="added", grams=grams, occurred_at=_iso(bought, 11))

    active = items_repo.list_active(conn, user_id)
    scored = risk_service.score_pantry(conn, user_id, kn)
    return {
        "user_id": user_id, "email": DEMO_EMAIL, "password": DEMO_PASSWORD,
        "active_items": len(active), "resolved_items": resolved,
        "wasted_items": wasted,
        "waste_rate_by_count": round(wasted / max(1, resolved), 4),
        "critical_now": sum(1 for s in scored if s["risk_band"] == "critical"),
        "history_days": HISTORY_DAYS,
        "unknown_food_ids": missing,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed the FridgeSense demo household")
    parser.add_argument("--reset", action="store_true",
                        help="drop every table first (deletes all accounts)")
    parser.add_argument("--seed", type=int, default=20260825)
    args = parser.parse_args()

    if args.reset:
        db.reset_db()
        print("database reset")
    else:
        db.init_db()

    with db.session() as conn:
        report = seed_demo(conn, args.seed)
    print("demo household ready")
    for key, value in report.items():
        print("  %-20s %s" % (key, value))
    print("\nlog in with %s / %s" % (DEMO_EMAIL, DEMO_PASSWORD))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
