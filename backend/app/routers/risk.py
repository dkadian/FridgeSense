from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import current_user, get_conn, get_kn
from ..knowledge import Knowledge
from ..services import risk_service

router = APIRouter(prefix="/api/risk", tags=["risk"])


@router.get("/eat-first", summary="The Eat Me First queue")
def eat_first(limit: int = Query(10, ge=1, le=100),
              min_risk: float = Query(0.0, ge=0.0, le=1.0),
              user: dict = Depends(current_user),
              conn: sqlite3.Connection = Depends(get_conn),
              kn: Knowledge = Depends(get_kn)):
    scored = risk_service.score_pantry(conn, user["id"], kn)
    shortlist = [s for s in scored if s["risk"] >= min_risk][:limit]
    return {"items": shortlist, "summary": risk_service.pantry_summary(scored, kn),
            "total_active": len(scored)}


@router.get("/item/{item_id}", summary="Risk and attributions for one item")
def item_risk(item_id: int, user: dict = Depends(current_user),
              conn: sqlite3.Connection = Depends(get_conn),
              kn: Knowledge = Depends(get_kn)):
    scored = risk_service.risk_for_item(conn, user["id"], item_id, kn)
    if scored is None:
        raise HTTPException(status_code=404, detail="Item not found")
    return scored


@router.get("/model", summary="Model card: metrics, baselines, limitations")
def model_card(kn: Knowledge = Depends(get_kn)):
    if not kn.model_card:
        raise HTTPException(status_code=503,
                            detail="No model card found. Run python3 ml/train_spoilage.py")
    card = dict(kn.model_card)
    if kn.model is not None:
        card["serving"] = {
            "trees": len(kn.model.trees),
            "features": list(kn.model.feature_names_),
            "operating_threshold": getattr(kn, "operating_threshold", 0.5),
        }
    return card
