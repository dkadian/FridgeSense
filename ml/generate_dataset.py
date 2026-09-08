"""Generates the training dataset for the FridgeSense spoilage-risk model.

WHY SYNTHETIC DATA
------------------
There is no openly available, item-level, labelled dataset of *which specific
household grocery items ended up in the bin*. Published sources (UNEP Food Waste
Index, WRAP, FAO) report aggregate mass per capita, not per-item outcomes. So
this script builds a behavioural simulator whose *aggregate* behaviour is
calibrated to those published figures, and whose per-item outcomes follow an
explicit, documented causal structure.

CAUSAL STRUCTURE
----------------
The dominant real-world driver of household food waste is buying more of a
perishable item than the household can consume before it spoils. The simulator
encodes that directly:

    surplus = days_of_stock / (shelf_life * engagement)
    days_of_stock = grams_bought / (daily_need_per_person * household_size)

and adds the secondary drivers documented in the WRAP household studies:
low planning ability, wrong storage choice, a crowded fridge (items get
forgotten), packages already opened, and cooked leftovers being especially
short-lived.

Crucially the simulator also carries *latent* household traits (planning skill,
cooking engagement) that the model is NOT given directly. The model only sees
what a real app could observe, including the household's own past waste rate as
a noisy proxy. That keeps the achievable accuracy realistic instead of perfect.

TWO CORRECTIONS MADE AFTER READING THE FIRST MODEL'S OUTPUT
----------------------------------------------------------
Both were found by scoring a real seeded pantry and asking whether the numbers
were defensible, which is worth more than any aggregate metric.

1. Quantity features are now scale-free. The first version fed raw
   `grams_remaining` and `grams_per_person` to the model. Those carry a real
   signal - food destined for the bin is eaten more slowly, so more of it is left
   at any given moment - but they also encode how a food is *sold*. The model
   duly learned that large masses mean waste and started rating a 3.5 kg bag of
   flour with five months of life left at 0.34, purely for being a big bag. The
   signal is kept in normalised form (`frac_pack_remaining`, and days of eating
   rather than grams), so "a lot" now means a lot relative to the household's own
   consumption instead of a lot in kilograms.

2. Features use only observable quantities. `days_of_stock` was previously
   computed with the household's latent `engagement`, which a real app cannot
   see, so the training features disagreed with what the serving code could
   compute by a factor of 1/engagement. Engagement now affects only the waste
   label and the consumption rate - where it causally belongs - while the
   features use the observable daily need. The latent trait stays latent.

HONEST LIMITATION
-----------------
A model trained here learns the simulator's assumptions. It is a credible
decision-support prior for a cold-start user, and the API is built to log real
outcomes so the model can be retrained on genuine data. It is not a claim of
validated real-world accuracy. This is stated in the model card and the report.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(REPO, "backend"))

DATA = os.path.join(REPO, "data")

# Relative frequency with which a category shows up in a shopping basket.
CATEGORY_WEIGHT = {
    "vegetables": 26.0, "leafy_greens": 7.0, "herbs": 5.0, "fruits": 14.0,
    "dairy": 12.0, "eggs": 4.0, "meat_fish": 5.0, "grains": 7.0,
    "pulses": 5.0, "bakery": 6.0, "cooked_leftovers": 9.0, "condiments": 4.0,
    "beverages": 1.5, "snacks": 3.0, "frozen": 2.0, "nuts_oils": 3.0,
}

FEATURES = [
    "days_to_expiry",
    "shelf_life_days",
    "frac_life_remaining",
    "days_since_purchase",
    "frac_pack_remaining",
    "days_of_stock_left",
    "finish_ratio",
    "storage_code",
    "opened",
    "perishability",
    "days_of_stock",
    "stock_vs_shelf",
    "storage_mismatch",
    "same_category_count",
    "active_items_total",
    "is_leftover",
    "household_size",
    "user_category_waste_rate",
    "user_overall_waste_rate",
]

STORAGE_CODE = {"pantry": 0, "fridge": 1, "freezer": 2}


def load_catalog():
    with open(os.path.join(DATA, "food_catalog.csv")) as fh:
        rows = list(csv.DictReader(fh))
    for r in rows:
        for k in ("perishability", "shelf_pantry", "shelf_fridge", "shelf_freezer",
                  "grams_per_unit", "daily_g_per_person"):
            r[k] = float(r[k])
    return rows


def shelf_for(row, storage):
    return row["shelf_%s" % storage]


def allowed_storages(row):
    return [s for s in ("pantry", "fridge", "freezer") if shelf_for(row, s) > 0]


def best_shelf(row):
    return max(shelf_for(row, s) for s in ("pantry", "fridge", "freezer"))


def sigmoid(z):
    return 1.0 / (1.0 + np.exp(-z))


def simulate(n_households=900, days=120, seed=7, appetite=1.0, rate_only=False):
    rng = np.random.default_rng(seed)
    catalog = load_catalog()

    weights = np.array([CATEGORY_WEIGHT.get(r["category"], 1.0) for r in catalog], dtype=float)
    # Within a category, spread the weight across its members.
    cat_counts = {}
    for r in catalog:
        cat_counts[r["category"]] = cat_counts.get(r["category"], 0) + 1
    for i, r in enumerate(catalog):
        weights[i] /= cat_counts[r["category"]]
    weights /= weights.sum()

    rows = []
    for hh in range(n_households):
        size = int(rng.choice([1, 2, 3, 4, 5, 6], p=[.12, .22, .26, .24, .11, .05]))
        planning = float(rng.beta(2.6, 2.2))            # 0 = chaotic, 1 = meticulous
        engagement = float(np.clip(rng.normal(0.95, 0.28), 0.35, 1.6))  # cooks at home
        organisation = float(rng.beta(2.4, 2.4))        # how visible the fridge is
        overbuy = float(np.clip(rng.normal(1.05, 0.35), 0.55, 2.6))     # basket inflation

        # Running personal history, used to build the observable history features.
        hist_total, hist_wasted = 0.0, 0.0
        cat_total, cat_wasted = {}, {}
        active_timeline = []   # (purchase_day, resolve_day, category)

        day = 0
        trip_gap = float(np.clip(rng.normal(4.0, 1.4), 1.5, 9.0))
        while day < days:
            n_items = int(np.clip(rng.poisson(2.0 + 0.9 * size), 1, 14))
            picks = rng.choice(len(catalog), size=n_items, replace=False, p=weights)
            for pi in picks:
                row = catalog[pi]
                opts = allowed_storages(row)
                if not opts:
                    continue
                default = row["storage_default"]
                if default in opts and rng.random() < 0.55 + 0.4 * organisation:
                    storage = default
                else:
                    storage = str(rng.choice(opts))

                shelf = shelf_for(row, storage)
                shelf_eff = max(1.0, shelf * float(np.clip(rng.normal(1.0, 0.16), 0.5, 1.6)))

                units = 1 + int(rng.random() < 0.30) + int(rng.random() < 0.10)
                grams = row["grams_per_unit"] * units * overbuy
                grams *= float(np.clip(rng.normal(1.0, 0.18), 0.5, 2.0))

                # Observable: what the app can compute from the catalog and the
                # stated household size. Engagement is latent and must not leak in.
                daily_need = max(1.0, row["daily_g_per_person"] * size)
                days_of_stock = grams / daily_need
                stock_vs_shelf = days_of_stock / shelf_eff
                mismatch = (best_shelf(row) - shelf) / max(best_shelf(row), 1.0)
                opened = int(rng.random() < (0.35 if row["category"] in
                             ("dairy", "condiments", "snacks", "frozen", "bakery") else 0.12))
                is_leftover = int(row["category"] == "cooked_leftovers")

                # Fridge crowding at the moment of purchase.
                active_now = sum(1 for (p0, r0, _c) in active_timeline if p0 <= day <= r0)
                crowd_z = (active_now - 18.0) / 12.0

                # ------------------------------------------------ consumption
                # Waste is not drawn from a coin flip here. It is the outcome of a
                # race: can this household get through this much food before the
                # date? The latent traits set the pace of eating and the label falls
                # out of the arithmetic.
                base_rate = appetite * engagement * (1.0 + 0.30 * (planning - 0.5))

                # The rate before we look in the fridge and the rate after are
                # separate draws around the same mean. This is deliberate, and it is
                # where the irreducible uncertainty of the problem lives: a snapshot
                # tells you how fast a pack has been going, not whether next week's
                # cooking will finish it. Without the split the features pin the
                # outcome down exactly and the model scores a meaningless AUC of
                # 1.000 - which is what happened when an earlier version of this
                # simulator set the consumption rate from the already-decided label.
                rate_before = max(0.02, base_rate * float(np.exp(rng.normal(0.0, 0.45))))
                rate_after = max(0.02, base_rate * float(np.exp(rng.normal(0.0, 0.45))))

                # Out of sight is a different failure mode from slow to cook.
                # Leftovers are the clearest case of this failure mode: nobody
                # refuses them on principle, they just stop being appealing by the
                # third day and quietly stay in the container.
                p_forgotten = sigmoid(-1.30 + 1.70 * (1.0 - organisation)
                                      + 0.50 * crowd_z + 0.60 * mismatch
                                      + 1.00 * is_leftover)
                if rng.random() < p_forgotten:
                    rate_after *= 0.12

                expiry_day = day + shelf_eff
                # The item sits in the kitchen until it is finished, or until it has
                # been past its date long enough to be thrown out. Observe it at a
                # random point in that window, which is what the app would see.
                finish_pre = grams / (daily_need * rate_before)
                present_until = min(finish_pre, shelf_eff + float(rng.uniform(0.0, 4.0)))
                snap = day + float(rng.uniform(0.0, max(0.5, present_until)))

                elapsed = snap - day
                grams_remaining = max(grams * 0.03,
                                      grams - daily_need * rate_before * elapsed)

                # Time still needed, at the household's future pace, against time
                # still available before the food stops being worth eating.
                t_need = grams_remaining / (daily_need * rate_after)
                t_avail = max(0.0, expiry_day - snap)
                # Poor storage can bring the real deadline forward of the label.
                p_spoil = sigmoid(-2.40 + 1.90 * mismatch
                                  + 0.60 * ((row["perishability"] - 1.0) / 4.0)
                                  + 0.45 * opened)
                if rng.random() < p_spoil:
                    t_avail *= float(rng.uniform(0.30, 0.80))

                wasted = int(t_need > t_avail)
                # Nobody follows the printed date exactly. Some food is eaten a
                # little late; some is binned while it is still perfectly good.
                if wasted and rng.random() < 0.22:
                    wasted = 0
                elif not wasted and rng.random() < 0.05:
                    wasted = 1

                resolve = (expiry_day + float(rng.uniform(0.0, 3.0)) if wasted
                           else snap + min(t_need, t_avail))

                cw_n = cat_total.get(row["category"], 0.0)
                cw_w = cat_wasted.get(row["category"], 0.0)
                # Laplace-style smoothing toward the 0.22 global prior.
                cat_rate = (cw_w + 2.0 * 0.22) / (cw_n + 2.0)
                all_rate = (hist_wasted + 4.0 * 0.22) / (hist_total + 4.0)

                same_cat = sum(1 for (p0, r0, c0) in active_timeline
                               if c0 == row["category"] and p0 <= snap <= r0)
                active_at_snap = sum(1 for (p0, r0, _c) in active_timeline if p0 <= snap <= r0)

                if rate_only:
                    rows.append(wasted)
                    active_timeline.append((day, resolve, row["category"]))
                    hist_total += 1.0
                    hist_wasted += wasted
                    cat_total[row["category"]] = cw_n + 1.0
                    cat_wasted[row["category"]] = cw_w + wasted
                    continue

                rows.append({
                    "household_id": hh,
                    "food_id": row["id"],
                    "category": row["category"],
                    "days_to_expiry": round(expiry_day - snap, 3),
                    "shelf_life_days": round(shelf_eff, 3),
                    "frac_life_remaining": round(
                        float(np.clip((expiry_day - snap) / shelf_eff, -1.0, 1.0)), 4),
                    "days_since_purchase": round(snap - day, 3),
                    "frac_pack_remaining": round(grams_remaining / max(1.0, grams), 4),
                    "days_of_stock_left": round(grams_remaining / daily_need, 3),
                    # Days of eating left over days available to eat it. Above 1
                    # the household cannot realistically finish it in time.
                    # Clamped because a nearly-expired sack gives a useless outlier.
                    "finish_ratio": round(float(np.clip(
                        (grams_remaining / daily_need) / max(0.5, expiry_day - snap),
                        0.0, 20.0)), 4),
                    "storage_code": STORAGE_CODE[storage],
                    "opened": opened,
                    "perishability": int(row["perishability"]),
                    "days_of_stock": round(days_of_stock, 3),
                    "stock_vs_shelf": round(stock_vs_shelf, 4),
                    "storage_mismatch": round(mismatch, 4),
                    "same_category_count": same_cat,
                    "active_items_total": active_at_snap,
                    "is_leftover": is_leftover,
                    "household_size": size,
                    "user_category_waste_rate": round(cat_rate, 4),
                    "user_overall_waste_rate": round(all_rate, 4),
                    "wasted": wasted,
                })

                active_timeline.append((day, resolve, row["category"]))
                hist_total += 1.0
                hist_wasted += wasted
                cat_total[row["category"]] = cw_n + 1.0
                cat_wasted[row["category"]] = cw_w + wasted

            day += max(1.0, rng.normal(trip_gap, 1.0))

    return rows


def calibrate_appetite(target=0.22, n_households=110, days=70, seed=99,
                       lo=0.15, hi=4.0, iters=16, verbose=True):
    """Solve for the one free parameter so the simulator's aggregate item-level
    waste incidence matches a published benchmark.

    The structural coefficients encode *relative* risk, which is what the model
    needs to learn; only the overall level is free. Fixing it by bisection against
    the UNEP Food Waste Index household figure keeps the dataset honest about
    having exactly one calibration knob rather than a hand-tuned intercept.

    Appetite scales how fast households eat, so the waste rate falls as it rises -
    the opposite direction to the logistic intercept this replaced.
    """
    def rate_at(a):
        out = simulate(n_households, days, seed, appetite=a, rate_only=True)
        return float(np.mean(out)) if out else 0.0

    for _ in range(iters):
        mid = 0.5 * (lo + hi)
        if rate_at(mid) > target:
            lo = mid                     # eating too slowly, wasting too much
        else:
            hi = mid
    a = 0.5 * (lo + hi)
    if verbose:
        print("calibrated appetite: %.4f  (probe rate %.4f, target %.3f)"
              % (a, rate_at(a), target))
    return a


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--households", type=int, default=520)
    ap.add_argument("--days", type=int, default=100)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default=os.path.join(HERE, "artifacts", "spoilage_dataset.csv"))
    ap.add_argument("--target-rate", type=float, default=0.22,
                    help="aggregate item-level waste incidence to calibrate to")
    args = ap.parse_args()

    appetite = calibrate_appetite(target=args.target_rate, seed=args.seed + 1)
    rows = simulate(args.households, args.days, args.seed, appetite=appetite)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    cols = (["household_id", "food_id", "category"] + FEATURES + ["wasted"])
    with open(args.out, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        w.writerows(rows)

    y = np.array([r["wasted"] for r in rows], dtype=float)
    print("rows: %d   households: %d" % (len(rows), args.households))
    print("overall waste rate: %.3f  (calibration target %.3f)" % (y.mean(), args.target_rate))
    print("written -> %s" % args.out)

    import collections
    by_cat = collections.defaultdict(list)
    for r in rows:
        by_cat[r["category"]].append(r["wasted"])
    print("\nwaste rate by category (sanity check - perishables must rank highest)")
    for c, v in sorted(by_cat.items(), key=lambda kv: -np.mean(kv[1])):
        print("  %-18s %.3f  n=%d" % (c, float(np.mean(v)), len(v)))


if __name__ == "__main__":
    main()
