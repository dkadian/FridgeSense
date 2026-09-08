from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, Query

from ..deps import current_user, get_conn, get_kn
from ..knowledge import Knowledge
from ..repositories import events as events_repo
from ..services import impact_service, insights_service

router = APIRouter(prefix="/api/impact", tags=["impact"])


@router.get("/summary", summary="Headline impact for a window")
def summary(days: int = Query(30, ge=1, le=365), user: dict = Depends(current_user),
            conn: sqlite3.Connection = Depends(get_conn),
            kn: Knowledge = Depends(get_kn)):
    return impact_service.summary(conn, user["id"], days, kn)


@router.get("/timeseries", summary="Daily waste, consumption and rolling waste rate")
def timeseries(days: int = Query(30, ge=7, le=365), user: dict = Depends(current_user),
               conn: sqlite3.Connection = Depends(get_conn),
               kn: Knowledge = Depends(get_kn)):
    return impact_service.timeseries(conn, user["id"], days, kn)


@router.get("/breakdown", summary="Waste split by category, food and reason")
def breakdown(days: int = Query(90, ge=7, le=365), user: dict = Depends(current_user),
              conn: sqlite3.Connection = Depends(get_conn),
              kn: Knowledge = Depends(get_kn)):
    return impact_service.breakdown(conn, user["id"], days, kn)


@router.get("/events", summary="Raw event log")
def events(limit: int = Query(50, ge=1, le=500), user: dict = Depends(current_user),
           conn: sqlite3.Connection = Depends(get_conn)):
    rows = events_repo.recent(conn, user["id"], limit)
    return {"events": [dict(r) for r in rows], "count": len(rows)}


@router.get("/insights", summary="Habit insights with evidence and projections")
def insights(window_days: int = Query(90, ge=7, le=365),
             user: dict = Depends(current_user),
             conn: sqlite3.Connection = Depends(get_conn),
             kn: Knowledge = Depends(get_kn)):
    return insights_service.generate(conn, user["id"], window_days, kn)
