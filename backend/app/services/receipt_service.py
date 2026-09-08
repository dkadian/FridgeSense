"""Turn pasted receipt text into a reviewable list of pantry items.

Receipt lines are hostile input: abbreviated ('TOMATO LOOSE 1KG'), padded with
till codes and tax columns, and inconsistently cased. The matcher blends
character-trigram cosine similarity with a sequence ratio over a 458-surface-form
lexicon built from the catalog, which handles both truncation and typos.

Nothing here writes to the database. Parsing returns candidates with confidence
scores and alternatives, and the user confirms them; silently importing a
mis-read line would poison the very history the model and insights depend on.
"""
from __future__ import annotations

import datetime as dt
import re

from ..knowledge import Knowledge, get_knowledge
from ..ml.matcher import parse_quantity, strip_noise
from . import pantry_service

HIGH_CONFIDENCE = 0.62
LOW_CONFIDENCE = 0.40

# Lines that are structure rather than purchases.
SKIP_PATTERNS = [
    re.compile(p, re.I) for p in (
        r"^\s*$",
        r"\b(total|subtotal|sub total|grand total|net amount|amount payable)\b",
        r"\b(gst|cgst|sgst|igst|vat|tax|round\s*off|discount|savings)\b",
        r"\b(cash|card|upi|change|tender|balance|paid|payment|wallet)\b",
        r"\b(invoice|bill no|receipt|gstin|tin no|pan|cin)\b",
        r"\b(thank you|visit again|customer copy|terms|helpline|cashier|counter)\b",
        r"\b(items?\s*[:=]?\s*\d+\s*$|qty\s*total)\b",
        r"^[-=*_.\s]+$",
        r"^\d[\d\s/:.-]*$",                      # bare dates, times, numbers
        r"\b(pvt\.?\s*ltd|supermarket|hypermarket|stores?|mart|bazaar)\b",
        # Non-food lines that appear on almost every Indian retail receipt.
        r"\b(carry\s*bag|plastic\s*bag|shopping\s*bag|bag\s*charge)",
        r"\b(loyalty|reward\s*points?|membership|coupon|redeem)\b",
        r"\b(delivery\s*(charge|fee)|packing\s*charge|service\s*charge|tip)\b",
    )
]

# Mass resolution constants.
PIECES_PER_CATALOG_UNIT = {"dozen": 12}     # catalog sells eggs by the dozen
BULK_CATALOG_UNITS = {"kg", "litre"}        # sold by weight, so no per-piece mass
ASSUMED_PIECE_GRAMS = 150.0                 # only used as a flagged fallback


def resolve_mass(qty: dict, food) -> tuple[float, str, bool]:
    """Work out how many grams a receipt line represents.

    Returns (grams, human explanation, whether the figure is an assumption).
    The explanation is surfaced in the UI because a wrong mass silently corrupts
    every downstream number, so the user needs to see how it was derived.
    """
    if qty.get("grams"):
        return float(qty["grams"]), "read from the receipt", False

    count = qty.get("count")
    if not count:
        return (float(food.grams_per_unit),
                "assumed one %s (%d g)" % (food.unit, food.grams_per_unit), True)

    if qty.get("kind") == "piece":
        if food.unit in BULK_CATALOG_UNITS:
            # A piece count cannot be converted without a per-piece mass, which
            # the catalog does not carry for anything sold loose by weight.
            return (count * ASSUMED_PIECE_GRAMS,
                    "%g pieces at an assumed %d g each - %s is priced by the %s, so "
                    "please check" % (count, ASSUMED_PIECE_GRAMS, food.name.lower(),
                                      food.unit), True)
        per_piece = food.grams_per_unit / PIECES_PER_CATALOG_UNIT.get(food.unit, 1)
        return (count * per_piece,
                "%g pieces x %d g" % (count, round(per_piece)), False)

    return (count * food.grams_per_unit,
            "%g x %s (%d g each)" % (count, food.unit, food.grams_per_unit), False)


def _skip(line: str) -> bool:
    return any(p.search(line) for p in SKIP_PATTERNS)


def parse_receipt(text: str, kn: Knowledge | None = None,
                  purchase_date: str | None = None) -> dict:
    kn = kn or get_knowledge()
    today = dt.date.today()
    bought = today
    if purchase_date:
        try:
            bought = dt.date.fromisoformat(str(purchase_date)[:10])
        except ValueError:
            bought = today

    raw_lines = [ln.strip() for ln in (text or "").replace("\r", "\n").split("\n")]
    items, unmatched, skipped = [], [], []

    for lineno, raw in enumerate(raw_lines, start=1):
        if not raw:
            continue
        if _skip(raw):
            skipped.append({"line": lineno, "text": raw, "reason": "not a product line"})
            continue

        qty = parse_quantity(raw)
        cleaned = strip_noise(raw)
        if len(cleaned) < 2:
            skipped.append({"line": lineno, "text": raw, "reason": "nothing left after cleaning"})
            continue

        matches = kn.matcher.match(cleaned, top_k=4)
        if not matches:
            unmatched.append({"line": lineno, "text": raw, "cleaned": cleaned,
                              "reason": "no catalog match above threshold"})
            continue

        best = matches[0]
        food = kn.food(best["food_id"])
        if food is None:
            unmatched.append({"line": lineno, "text": raw, "cleaned": cleaned,
                              "reason": "matched an id missing from the catalog"})
            continue

        grams, source, assumed = resolve_mass(qty, food)

        storage = food.storage_default
        expiry = pantry_service.default_expiry(food, storage, bought)
        confidence = float(best["score"])
        items.append({
            "line": lineno,
            "raw": raw,
            "cleaned": cleaned,
            "matched_text": best.get("surface", cleaned),
            "food_id": food.id,
            "name": food.name,
            "category": food.category,
            "grams": round(float(grams), 1),
            "grams_source": source,
            "unit": food.unit,
            "grams_per_unit": food.grams_per_unit,
            "storage": storage,
            "purchase_date": bought.isoformat(),
            "expiry_date": expiry.isoformat(),
            "shelf_life_days": int(food.shelf_days(storage)),
            "quantity_assumed": assumed,
            "confidence": round(confidence, 3),
            "needs_review": bool(confidence < HIGH_CONFIDENCE or assumed),
            "review_reason": ("low name-match confidence" if confidence < HIGH_CONFIDENCE
                              else ("quantity was assumed" if assumed else "")),
            "co2e_kg": round(float(grams) / 1000.0 * food.co2e_kg_per_kg, 3),
            "value_inr": round(float(grams) / 1000.0 * food.price_inr_per_kg, 2),
            "alternatives": [
                {"food_id": m["food_id"],
                 "name": kn.food(m["food_id"]).name if kn.food(m["food_id"]) else m["food_id"],
                 "score": round(float(m["score"]), 3)}
                for m in matches[1:4]
            ],
        })

    confident = [i for i in items if not i["needs_review"]]
    return {
        "purchase_date": bought.isoformat(),
        "items": items,
        "unmatched": unmatched,
        "skipped": skipped,
        "stats": {
            "lines_read": len([l for l in raw_lines if l]),
            "matched": len(items),
            "high_confidence": len(confident),
            "needs_review": len(items) - len(confident),
            "unmatched": len(unmatched),
            "skipped": len(skipped),
            "match_rate": round(len(items) / max(1, len(items) + len(unmatched)), 3),
            "total_grams": round(sum(i["grams"] for i in items), 1),
            "total_value_inr": round(sum(i["value_inr"] for i in items), 2),
            "total_co2e_kg": round(sum(i["co2e_kg"] for i in items), 3),
        },
        "thresholds": {"high_confidence": HIGH_CONFIDENCE, "low_confidence": LOW_CONFIDENCE},
        "note": ("Nothing has been saved yet. Confirm the list to add it to your pantry, "
                 "and correct any row flagged for review first."),
    }


def confirm(conn, user_id: int, entries: list[dict], kn: Knowledge | None = None) -> dict:
    """Commit a reviewed parse. Only whitelisted fields cross into the pantry."""
    kn = kn or get_knowledge()
    payload = []
    for e in entries:
        payload.append({
            "food_id": e.get("food_id"),
            "grams": e.get("grams"),
            "storage": e.get("storage"),
            "purchase_date": e.get("purchase_date"),
            "expiry_date": e.get("expiry_date"),
            "notes": "imported from receipt",
        })
    return pantry_service.add_many(conn, user_id, payload, kn)
