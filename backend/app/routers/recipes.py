from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import current_user, get_conn, get_kn
from ..knowledge import Knowledge
from ..schemas import AiRecipeGenerateRequest, CookRequest, CustomRecipeCookRequest
from ..services import llm_service, pantry_service, recipe_service, risk_service

router = APIRouter(prefix="/api/recipes", tags=["recipes"])


@router.get("/suggest", summary="Recipes ranked by what they rescue")
def suggest(limit: int = Query(10, ge=1, le=40),
            meal: str = Query("any"), diet: str = Query("any"),
            max_minutes: int | None = Query(None, ge=5, le=240),
            require_rescue: bool = Query(False),
            user: dict = Depends(current_user),
            conn: sqlite3.Connection = Depends(get_conn),
            kn: Knowledge = Depends(get_kn)):
    return recipe_service.suggest(conn, user["id"], kn, limit=limit, meal=meal,
                                  diet=diet, max_minutes=max_minutes,
                                  require_rescue=require_rescue)


@router.get("/plan", summary="Greedy multi-day plan that maximises rescued food")
def plan(days: int = Query(3, ge=1, le=7), user: dict = Depends(current_user),
         conn: sqlite3.Connection = Depends(get_conn),
         kn: Knowledge = Depends(get_kn)):
    return recipe_service.meal_plan(conn, user["id"], days, kn)


@router.post("/ai-generate", summary="Synthesize custom zero-waste recipe tailored to at-risk items")
def ai_generate(payload: AiRecipeGenerateRequest,
                user: dict = Depends(current_user),
                conn: sqlite3.Connection = Depends(get_conn),
                kn: Knowledge = Depends(get_kn)):
    scored = risk_service.score_pantry(conn, user["id"], kn)
    at_risk = [s for s in scored if s["risk"] >= 0.40 or s["days_to_expiry"] <= 2]
    if payload.target_item_ids:
        target_set = set(payload.target_item_ids)
        at_risk = [s for s in scored if s["item_id"] in target_set] or at_risk

    return llm_service.generate_zero_waste_recipe(
        at_risk_items=at_risk,
        pantry_items=scored,
        meal=payload.meal,
        diet=payload.diet,
        preferences=payload.preferences,
        kn=kn,
    )


@router.post("/cook-custom", summary="Deduct a custom or AI-generated recipe from the pantry")
def cook_custom(payload: CustomRecipeCookRequest,
                user: dict = Depends(current_user),
                conn: sqlite3.Connection = Depends(get_conn),
                kn: Knowledge = Depends(get_kn)):
    ingredients = [i.model_dump() for i in payload.ingredients]
    return pantry_service.cook_custom_recipe(
        conn, user["id"], payload.title, ingredients, payload.servings, kn)


@router.get("/{recipe_id}", summary="One recipe with full steps")
def get_recipe(recipe_id: str, kn: Knowledge = Depends(get_kn)):
    recipe = kn.recipe_by_id.get(recipe_id)
    if recipe is None:
        raise HTTPException(status_code=404, detail="No such recipe: %s" % recipe_id)
    enriched = dict(recipe)
    enriched["ingredients"] = [
        {**ing, "name": (kn.food(ing["id"]).name if kn.food(ing["id"]) else ing["id"])}
        for ing in recipe["ingredients"]
    ]
    return enriched


@router.post("/{recipe_id}/cook", summary="Deduct a recipe's ingredients from the pantry")
def cook(recipe_id: str, payload: CookRequest, user: dict = Depends(current_user),
         conn: sqlite3.Connection = Depends(get_conn),
         kn: Knowledge = Depends(get_kn)):
    try:
        return pantry_service.cook_recipe(conn, user["id"], recipe_id,
                                          payload.servings, kn)
    except pantry_service.PantryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

