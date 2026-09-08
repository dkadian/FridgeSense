from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import get_kn
from ..knowledge import Knowledge, category_title

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


def food_payload(food) -> dict:
    return {
        "id": food.id, "name": food.name, "category": food.category,
        "category_label": category_title(food.category),
        "perishability": food.perishability,
        "storage_default": food.storage_default,
        "recommended_storage": food.recommended_storage,
        "shelf_life_days": {k: v for k, v in food.shelf.items()},
        "co2e_kg_per_kg": food.co2e_kg_per_kg,
        "water_l_per_kg": food.water_l_per_kg,
        "price_inr_per_kg": food.price_inr_per_kg,
        "unit": food.unit, "grams_per_unit": food.grams_per_unit,
        "daily_g_per_person": food.daily_g_per_person,
        "freezer_gain_days": food.freezer_gain(food.storage_default),
        "ethylene_type": food.ethylene_type,
        "ethylene_tip": food.ethylene_tip,
        "ethylene_antagonists": food.ethylene_antagonists,
    }


@router.get("/foods", summary="Search the food catalog")
def foods(q: str = Query("", max_length=60), limit: int = Query(20, ge=1, le=200),
          category: str = Query("", max_length=40), kn: Knowledge = Depends(get_kn)):
    if category:
        found = [f for f in kn.foods.values() if f.category == category]
        found.sort(key=lambda f: f.name)
        found = found[:limit]
    else:
        found = kn.search_foods(q, limit)
    return {"count": len(found), "foods": [food_payload(f) for f in found]}


@router.get("/foods/{food_id}", summary="One food with its full factor set")
def food(food_id: str, kn: Knowledge = Depends(get_kn)):
    item = kn.food(food_id)
    if item is None:
        raise HTTPException(status_code=404, detail="No such food: %s" % food_id)
    return food_payload(item)


@router.get("/categories", summary="Categories with counts")
def categories(kn: Knowledge = Depends(get_kn)):
    counts = Counter(f.category for f in kn.foods.values())
    return {"categories": [
        {"category": c, "label": category_title(c), "foods": n}
        for c, n in sorted(counts.items())
    ]}


@router.get("/factors", summary="Impact factors, equivalences and their sources")
def factors(kn: Knowledge = Depends(get_kn)):
    return kn.factors
