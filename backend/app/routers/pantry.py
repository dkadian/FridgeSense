from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..deps import current_user, get_conn, get_kn
from ..knowledge import Knowledge
from ..repositories import items as items_repo
from ..schemas import (
    ItemBulkCreate,
    ItemCreate,
    ItemUpdate,
    ResolveRequest,
    RestockRequest,
    ScratchpadParseRequest,
)
from ..services import pantry_service, risk_service, scratchpad_service

router = APIRouter(prefix="/api/pantry", tags=["pantry"])



def _bad_request(exc: Exception):
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("", summary="Everything active, scored and sorted by risk")
def list_pantry(user: dict = Depends(current_user),
                conn: sqlite3.Connection = Depends(get_conn),
                kn: Knowledge = Depends(get_kn)):
    scored = risk_service.score_pantry(conn, user["id"], kn)
    return {"items": scored, "summary": risk_service.pantry_summary(scored, kn)}


@router.post("", status_code=status.HTTP_201_CREATED, summary="Add one item")
def add(payload: ItemCreate, user: dict = Depends(current_user),
        conn: sqlite3.Connection = Depends(get_conn), kn: Knowledge = Depends(get_kn)):
    try:
        return pantry_service.add_item(conn, user["id"], kn=kn, **payload.model_dump())
    except pantry_service.PantryError as exc:
        raise _bad_request(exc) from exc


@router.post("/bulk", status_code=status.HTTP_201_CREATED,
             summary="Add many items, reporting per-row failures")
def add_bulk(payload: ItemBulkCreate, user: dict = Depends(current_user),
             conn: sqlite3.Connection = Depends(get_conn),
             kn: Knowledge = Depends(get_kn)):
    return pantry_service.add_many(
        conn, user["id"], [i.model_dump() for i in payload.items], kn)


@router.post("/scratchpad", summary="Parse unstructured Hinglish text / WhatsApp notes into pantry candidates")
def parse_scratchpad(payload: ScratchpadParseRequest, user: dict = Depends(current_user),
                     kn: Knowledge = Depends(get_kn)):
    return scratchpad_service.parse_scratchpad_notes(payload.text, kn, payload.purchase_date)


@router.get("/restock-list", summary="Get prebuilt list of items previously bought that have run out")
def restock_list(user: dict = Depends(current_user),
                 conn: sqlite3.Connection = Depends(get_conn),
                 kn: Knowledge = Depends(get_kn)):
    items = pantry_service.get_restock_list(conn, user["id"], kn)
    return {"items": items, "count": len(items)}


@router.delete("/restock-list/{food_id}", summary="Dismiss an item from the restock list so it doesn't reappear")
def dismiss_restock(food_id: str, user: dict = Depends(current_user),
                    conn: sqlite3.Connection = Depends(get_conn)):
    return pantry_service.dismiss_restock_item(conn, user["id"], food_id)


@router.delete("/restock-list", summary="Clear/dismiss all current items from the restock list")
def clear_restock(user: dict = Depends(current_user),
                  conn: sqlite3.Connection = Depends(get_conn),
                  kn: Knowledge = Depends(get_kn)):
    return pantry_service.clear_restock_list(conn, user["id"], kn)


@router.post("/shopping-list/custom", summary="Add a custom item to shopping list")
def add_custom_shopping(payload: dict, user: dict = Depends(current_user),
                        conn: sqlite3.Connection = Depends(get_conn),
                        kn: Knowledge = Depends(get_kn)):
    name = str(payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Item name is required")
    category = str(payload.get("category") or "other")
    grams = float(payload.get("grams") or 500.0)
    unit = str(payload.get("unit") or "g")
    return pantry_service.add_custom_shopping_item(
        conn, user["id"], name=name, category=category, grams=grams, unit=unit, kn=kn
    )


@router.post("/restock", status_code=status.HTTP_201_CREATED, summary="1-click restock items into pantry")
def restock(payload: RestockRequest, user: dict = Depends(current_user),
            conn: sqlite3.Connection = Depends(get_conn),
            kn: Knowledge = Depends(get_kn)):
    return pantry_service.restock_items(
        conn, user["id"], [i.model_dump() for i in payload.items],
        purchase_date=payload.purchase_date, kn=kn
    )


@router.get("/history", summary="Items already consumed, wasted or donated")
def history(status_filter: str = Query("all", alias="status"),
            limit: int = Query(100, ge=1, le=500),
            user: dict = Depends(current_user),
            conn: sqlite3.Connection = Depends(get_conn)):
    rows = items_repo.list_all(conn, user["id"], status_filter, limit)
    return {"items": [dict(r) for r in rows], "count": len(rows)}


@router.get("/{item_id}", summary="One item with its risk explanation")
def get_item(item_id: int, user: dict = Depends(current_user),
             conn: sqlite3.Connection = Depends(get_conn),
             kn: Knowledge = Depends(get_kn)):
    scored = risk_service.risk_for_item(conn, user["id"], item_id, kn)
    if scored is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return scored


@router.patch("/{item_id}", summary="Edit an active item")
def update_item(item_id: int, payload: ItemUpdate,
                user: dict = Depends(current_user),
                conn: sqlite3.Connection = Depends(get_conn),
                kn: Knowledge = Depends(get_kn)):
    try:
        return pantry_service.update_item(conn, user["id"], item_id, kn=kn,
                                          **payload.model_dump())
    except pantry_service.PantryError as exc:
        raise _bad_request(exc) from exc


@router.delete("/{item_id}", summary="Remove a mis-entered item without logging impact")
def delete_item(item_id: int, user: dict = Depends(current_user),
                conn: sqlite3.Connection = Depends(get_conn)):
    try:
        return {"deleted": pantry_service.delete_item(conn, user["id"], item_id)}
    except pantry_service.PantryError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{item_id}/resolve", summary="Mark an item consumed, wasted or donated")
def resolve(item_id: int, payload: ResolveRequest,
            user: dict = Depends(current_user),
            conn: sqlite3.Connection = Depends(get_conn),
            kn: Knowledge = Depends(get_kn)):
    try:
        return pantry_service.resolve_item(conn, user["id"], item_id, payload.status,
                                           payload.grams, payload.waste_reason, kn)
    except pantry_service.PantryError as exc:
        raise _bad_request(exc) from exc


@router.post("/{item_id}/horizon-calibrate", summary="Calibrate or mark finished a bulk staple item")
def calibrate_horizon(item_id: int, payload: dict,
                      user: dict = Depends(current_user),
                      conn: sqlite3.Connection = Depends(get_conn),
                      kn: Knowledge = Depends(get_kn)):
    try:
        return pantry_service.calibrate_horizon(conn, user["id"], item_id, payload, kn=kn)
    except pantry_service.PantryError as exc:
        raise _bad_request(exc) from exc
