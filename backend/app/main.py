"""FastAPI application factory.

Two decisions here are worth stating, because both trade purity for the chance
that a reviewer sees a working app on the first try:

1. The schema is created at startup, not by a migration step. SQLite DDL is
   idempotent (`CREATE TABLE IF NOT EXISTS`), so this is safe to repeat, and it
   removes a step someone could skip.
2. If the database has no users at all, the demo household is seeded once. That
   only happens on a genuinely empty database, so it can never overwrite real
   data, and it can be turned off with FRIDGESENSE_AUTOSEED=0.

The knowledge base - food catalog, recipe index, receipt lexicon and the trained
spoilage model - is loaded once at startup rather than per request. It is a few
megabytes of read-only NumPy and dictionaries, and paying for it on every
request would dominate the response time of an endpoint that is otherwise
sub-millisecond.
"""
from __future__ import annotations

import contextlib
import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse

from . import config, db
from .knowledge import get_knowledge
from .routers import (ai, auth, catalog, impact, meta, pantry, receipts, recipes,
                      risk)


log = logging.getLogger("fridgesense")

DESCRIPTION = """
**FridgeSense** predicts which food in your kitchen is about to be thrown away,
and turns that prediction into something you can act on tonight.

The spoilage model is a gradient-boosted tree ensemble written from scratch on
NumPy and trained on a simulated panel of 900 households. It is deliberately
*not* a countdown to the printed date: two items expiring on the same day get
very different scores depending on how much is left, how fast this household
actually eats that food, whether it is stored where it should be, and how
crowded that shelf is.

Every score arrives with the reasons behind it, drawn from the model's own
per-feature attributions rather than written by hand. See `GET /api/meta` for
the model card, including where it performs poorly.
"""


def _autoseed() -> None:
    """Seeds the demo household, but only into a database with no users."""
    if os.environ.get("FRIDGESENSE_AUTOSEED", "1") not in ("1", "true", "yes"):
        return
    try:
        from seed import DEMO_EMAIL, seed_demo
        from .repositories import users as users_repo
    except ImportError as exc:
        log.warning("Auto-seed skipped, seed script not importable: %s", exc)
        return
    try:
        with db.session() as conn:
            if users_repo.count(conn) > 0:
                return
            report = seed_demo(conn)
        log.info("Seeded demo household %s: %d active items, %d resolved events",
                 DEMO_EMAIL, report["active_items"], report["resolved_items"])
    except Exception as exc:                      # pragma: no cover - defensive
        # A seeding failure must not stop the API from serving. An empty pantry
        # is recoverable through the UI; an unbootable app is not.
        log.warning("Auto-seed failed (%s: %s). The API is still up.",
                    type(exc).__name__, exc)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    kn = get_knowledge()
    for w in kn.warnings:
        log.warning("knowledge: %s", w)
    log.info("Loaded %d foods, %d recipes, spoilage model %s",
             len(kn.foods), len(kn.recipes),
             "ready" if kn.model is not None else "MISSING (heuristic fallback)")
    _autoseed()
    yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="FridgeSense API",
        description=DESCRIPTION,
        version=meta.APP_VERSION,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_tags=[
            {"name": "auth", "description": "Register, log in, and inspect the caller."},
            {"name": "pantry", "description": "The items in the kitchen and what happened to them."},
            {"name": "risk", "description": "Spoilage scores, ranked eat-me-first list, and per-item explanations."},
            {"name": "recipes", "description": "Recipes ranked by how much at-risk food they use up."},
            {"name": "receipt", "description": "Turn a pasted till receipt into pantry items."},
            {"name": "impact", "description": "Money, carbon and water accounting over the event log."},
            {"name": "catalog", "description": "The food knowledge base backing every estimate."},
            {"name": "ai", "description": "Gemini LLM status, coach, and key configuration."},
            {"name": "meta", "description": "Health, build metadata, and the demo reset."},
        ],
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in config.CORS_ORIGINS if o.strip()],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    for module in (auth, pantry, risk, recipes, receipts, impact, catalog, meta, ai):
        app.include_router(module.router)


    @app.get("/", include_in_schema=False)
    def root():
        return RedirectResponse(url="/docs")

    return app


app = create_app()
