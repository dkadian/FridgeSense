"""Health, build metadata and the demo reset.

The demo reset exists because the most common way to look at this project is to
clone it and want a populated dashboard within a minute. It is a deliberate
convenience with a deliberate limit: it only ever touches the single seeded demo
account, so it cannot be used to wipe a real user's pantry.
"""
from __future__ import annotations

import datetime as dt
import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from .. import config
from ..deps import get_conn, get_kn
from ..knowledge import Knowledge
from ..repositories import users as users_repo

router = APIRouter(prefix="/api", tags=["meta"])

APP_VERSION = "1.0.0"


@router.get("/health", summary="Liveness and readiness")
def health(conn: sqlite3.Connection = Depends(get_conn),
           kn: Knowledge = Depends(get_kn)):
    """Reports readiness per component rather than a bare 200.

    A pantry app whose spoilage model failed to load still answers requests, it
    just silently falls back to a shelf-life heuristic. Saying so here is more
    useful than claiming to be healthy.
    """
    try:
        conn.execute("SELECT 1").fetchone()
        db_ok = True
    except sqlite3.Error:
        db_ok = False

    return {
        "status": "ok" if (db_ok and kn.model is not None) else "degraded",
        "version": APP_VERSION,
        "time": dt.datetime.now().isoformat(timespec="seconds"),
        "components": {
            "database": "ok" if db_ok else "unavailable",
            "spoilage_model": "loaded" if kn.model is not None
                              else "missing - falling back to a shelf-life heuristic",
            "recipe_index": "loaded" if kn.recipe_matrix is not None else "missing",
            "receipt_lexicon": "loaded" if kn.matcher is not None else "missing",
        },
        "warnings": list(kn.warnings),
    }


@router.get("/meta", summary="What this build knows")
def meta(conn: sqlite3.Connection = Depends(get_conn),
         kn: Knowledge = Depends(get_kn)):
    card = kn.model_card or {}
    metrics = card.get("metrics_test") or {}
    return {
        "app": {"name": "FridgeSense", "version": APP_VERSION},
        "knowledge": {
            "foods": len(kn.foods),
            "categories": sorted({f.category for f in kn.foods.values()}),
            "recipes": len(kn.recipes),
            "impact_sources": kn.factors.get("meta", {}).get("sources", []),
        },
        "model": {
            "name": card.get("model_name"),
            "algorithm": card.get("algorithm"),
            "trained_at": card.get("trained_at"),
            "features": card.get("features", []),
            "auc": metrics.get("roc_auc"),
            "average_precision": metrics.get("average_precision"),
            "operating_threshold": getattr(kn, "operating_threshold", None),
            "loaded": kn.model is not None,
        },
        "database": {
            "path": config.DB_PATH,
            "users": users_repo.count(conn),
        },
        "warnings": list(kn.warnings),
    }


@router.post("/demo/reset", summary="Rebuild the demo household")
def demo_reset(conn: sqlite3.Connection = Depends(get_conn)):
    """Rebuilds only the demo account, leaving any other user untouched."""
    try:
        from seed import DEMO_EMAIL, DEMO_PASSWORD, seed_demo
    except ImportError as exc:            # pragma: no cover - packaging accident
        raise HTTPException(status_code=503,
                            detail="Seed script not importable: %s" % exc) from exc

    existing = users_repo.by_email(conn, DEMO_EMAIL)
    if existing is not None:
        # Items and events go with it via ON DELETE CASCADE.
        users_repo.delete(conn, int(existing["id"]))
        conn.commit()

    report = seed_demo(conn)
    conn.commit()
    return {
        "reset": True,
        "login": {"email": DEMO_EMAIL, "password": DEMO_PASSWORD},
        "report": report,
    }
