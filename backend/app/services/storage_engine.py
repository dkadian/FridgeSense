"""Storage and Packaging Calculation Engine.

Calculates accurate, food-science-backed shelf life and preservation multipliers
based on:
1. Food catalog baseline for the storage zone (pantry, fridge, freezer)
2. Container / packaging type (airtight, steel dabba, polythene bag, paper/mesh, open)
3. Covered status (sealed/covered vs exposed to air)

Prevents random drift or accumulation of days by computing deterministically
from purchase date.
"""
from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..knowledge import Food

STORAGES = ("pantry", "fridge", "freezer")
CONTAINERS = ("default", "airtight", "steel_dabba", "polythene", "paper_mesh", "open")

CONTAINER_LABELS = {
    "default": "Default / Original Pack",
    "airtight": "Airtight Container (Tupperware / Lock&Lock)",
    "steel_dabba": "Steel Dabba (Classic Indian Box)",
    "polythene": "Polythene / Plastic Bag",
    "paper_mesh": "Paper / Mesh / Cloth Bag",
    "open": "Open / Uncovered Plate / Bowl",
}


def base_shelf_for_storage(food: Food, storage: str) -> float:
    """Returns realistic base shelf life for the given food and storage zone."""
    storage = (storage or food.storage_default).lower()

    if storage == "pantry":
        # Perishable items like milk, chicken, cooked food spoil in ~1 day at Indian room temp
        if food.category in ("dairy", "meat_fish", "cooked_leftovers") or food.shelf.get("pantry", 0) <= 0:
            return 1.0
        return max(1.0, float(food.shelf.get("pantry", 3.0)))

    if storage == "fridge":
        fridge_days = food.shelf.get("fridge", 0)
        if fridge_days > 0:
            return float(fridge_days)
        # Dry staples kept in fridge keep standard dry shelf life
        if food.category in ("grains", "pulses", "spices", "condiments", "beverages"):
            return max(30.0, float(food.shelf.get("pantry", 60.0)))
        return 4.0

    if storage == "freezer":
        freezer_days = food.shelf.get("freezer", 0)
        if freezer_days <= 0:
            return 1.0  # Not recommended for freezing (e.g. cucumber, raw egg in shell)
        # Realistic home freezer quality retention (avoiding exaggerated 240+ day numbers)
        if food.category in ("dairy", "cooked_leftovers"):
            return min(float(freezer_days), 35.0)
        if food.category in ("leafy_greens", "herbs"):
            return min(float(freezer_days), 45.0)
        if food.category in ("meat_fish", "bakery"):
            return min(float(freezer_days), 60.0)
        if food.category in ("vegetables", "frozen"):
            return min(float(freezer_days), 90.0)
        return min(float(freezer_days), 90.0)

    return 4.0


def container_multiplier(food: Food, storage: str, container: str = "default") -> float:
    """Computes multiplier based on food characteristics and container physics."""
    c = str(container or "default").lower()

    if c == "airtight":
        # Critical exception: alliums & potatoes need air circulation! Airtight traps moisture & induces rot.
        if food.id in ("potato", "onion", "garlic"):
            return 0.70
        if food.category in ("leafy_greens", "herbs"):
            return 1.30  # Shields against dry fridge drafts and external ethylene
        if food.category in ("dairy", "cooked_leftovers"):
            return 1.25  # Prevents bacterial airborne cross-contamination and odor absorption
        if food.category in ("snacks", "bakery", "grains", "pulses"):
            return 1.35  # Blocks atmospheric humidity and sogging
        return 1.20

    if c == "steel_dabba":
        # Classic Indian kitchen staple: opaque (protects light-sensitive vitamins), cool, non-reactive
        if food.id in ("potato", "onion"):
            return 0.85
        if food.category in ("leafy_greens", "herbs", "vegetables", "dairy", "cooked_leftovers"):
            return 1.20
        return 1.15

    if c == "paper_mesh":
        # Breathable: absorbs moisture sweat without drying out
        if food.id in ("potato", "onion", "garlic"):
            return 1.30  # Ideal ventilation in cool pantry
        if food.category in ("leafy_greens", "herbs"):
            return 1.25  # Absorbs transpiration condensation, preventing leaf melting
        if food.id == "mushroom":
            return 1.35  # Prevents mushroom sliminess
        return 1.10

    if c == "polythene":
        # Traps condensation moisture
        if food.category in ("leafy_greens", "herbs"):
            return 0.80  # Trapped sweat causes rapid bacterial rot & slime
        if food.id in ("potato", "onion", "garlic"):
            return 0.65  # Sweating induces fungal mold and premature sprouting
        if food.category == "vegetables" and food.id in ("carrot", "radish", "beetroot"):
            return 1.10  # Prevents wilting of root vegetables
        return 0.95

    if c == "open":
        return 0.70  # Rapid dehydration, oxidation, odor contamination

    return 1.00  # default


def calculate_effective_shelf_days(food: Food, storage: str, container: str = "default",
                                   is_covered: bool = True) -> float:
    """Calculates overall effective shelf life in days with all factors combined."""
    base = base_shelf_for_storage(food, storage)
    c = str(container or "default").lower()
    c_mult = container_multiplier(food, storage, c)

    # Covered vs uncovered modifier
    if c == "open":
        cov_mult = 1.0  # Already factored in c_mult
    elif not is_covered:
        cov_mult = 0.75  # Uncovered penalty (dehydration + odor pickup)
    else:
        cov_mult = 1.00

    eff = base * c_mult * cov_mult
    return max(0.5, round(eff, 1))


def calculate_expiry_date(food: Food, storage: str, purchase_date: dt.date,
                          container: str = "default", is_covered: bool = True) -> dt.date:
    """Returns a 100% deterministic expiry date from purchase date."""
    eff_days = calculate_effective_shelf_days(food, storage, container, is_covered)
    days_to_add = int(max(1, round(eff_days)))
    return purchase_date + dt.timedelta(days=days_to_add)


def get_packaging_insight(food: Food, storage: str, container: str = "default",
                          is_covered: bool = True) -> dict:
    """Generates structured Co-Pilot insight and practical kitchen advice."""
    c = str(container or "default").lower()
    base = base_shelf_for_storage(food, storage)
    eff = calculate_effective_shelf_days(food, storage, c, is_covered)
    diff = round(eff - base, 1)
    pct = round(((eff - base) / max(0.1, base)) * 100)

    # Determine tone and practical Indian kitchen advice
    tone = "positive" if eff > base else ("negative" if eff < base else "neutral")

    advice = []
    if c == "airtight":
        if food.id in ("potato", "onion", "garlic"):
            advice.append("Airtight boxes trap moisture for potatoes and onions, causing rot and sprouting. Move to a breathable mesh basket or paper bag.")
            tone = "negative"
        elif food.category in ("leafy_greens", "herbs"):
            advice.append("Airtight seal protects greens from dry fridge air. Line with a dry paper towel to catch excess moisture.")
        else:
            advice.append("Airtight container shields food from external odors and slows microbial decay.")

    elif c == "steel_dabba":
        if food.id in ("potato", "onion"):
            advice.append("Steel dabbas with tight lids can trap moisture for onions/potatoes. Keep them in an open ventilated basket.")
            tone = "negative"
        else:
            advice.append("Classic Indian steel dabba: opaque protection prevents light oxidation and keeps contents cool and hygienic.")

    elif c == "paper_mesh":
        if food.id in ("potato", "onion", "garlic"):
            advice.append("Ideal aeration! Breathable paper or cloth bag prevents moisture accumulation and retards sprouting.")
        elif food.category in ("leafy_greens", "herbs"):
            advice.append("Paper/cloth absorbs natural leaf perspiration, preventing leaf slime and melting.")

    elif c == "polythene":
        if food.category in ("leafy_greens", "herbs"):
            advice.append("Closed polythene bags trap transpiration sweat, accelerating bacterial leaf rot. Transfer to a paper bag or container with a towel.")
            tone = "negative"
        elif food.id in ("potato", "onion", "garlic"):
            advice.append("Plastic bags cause potatoes and onions to sweat and develop black mold. Store loose in a cool dry pantry.")
            tone = "negative"
        else:
            advice.append("Basic plastic packaging: keeps loose items grouped but lacks breathability.")

    elif c == "open" or not is_covered:
        advice.append("Uncovered food suffers rapid moisture evaporation and absorbs strong fridge smells. Cover with a lid or plate.")
        tone = "negative"

    badge_text = ""
    if pct > 0:
        badge_text = f"+{pct}% Freshness Boost ({diff:+.1f}d)"
    elif pct < 0:
        badge_text = f"{pct}% Shelf Life Loss ({diff:+.1f}d)"
    else:
        badge_text = "Standard Baseline"

    return {
        "container": c,
        "is_covered": is_covered and c != "open",
        "base_days": base,
        "effective_days": eff,
        "diff_days": diff,
        "diff_pct": pct,
        "badge_text": badge_text,
        "tone": tone,
        "advice": advice[0] if advice else "Standard storage shelf life applies.",
    }
