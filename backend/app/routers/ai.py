from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends

from ..deps import current_user, get_conn, get_kn
from ..knowledge import Knowledge
from ..schemas import AiCoachRequest, AiKeyRequest
from ..services import llm_service, risk_service

router = APIRouter(prefix="/api/ai", tags=["ai"])


@router.get("/status", summary="Check Gemini AI integration status and active capabilities")
def status():
    return llm_service.get_ai_status()


@router.post("/key", summary="Set or update Gemini API key for this session")
def set_key(payload: AiKeyRequest):
    llm_service.set_runtime_api_key(payload.api_key)
    return {"status": "ok", "message": "API key updated", "ai_status": llm_service.get_ai_status()}


@router.post("/coach", summary="Ask the AI Food Rescue Coach practical food safety and storage questions")
def ask_coach(payload: AiCoachRequest,
              user: dict = Depends(current_user),
              conn: sqlite3.Connection = Depends(get_conn),
              kn: Knowledge = Depends(get_kn)):
    scored = risk_service.score_pantry(conn, user["id"], kn)
    answer = llm_service.ask_food_rescue_coach(
        user_message=payload.message,
        pantry_items=scored,
        history=payload.history,
    )
    return {
        "question": payload.message,
        "answer": answer,
        "mode": "gemini_live" if llm_service.is_live() else "smart_heuristic_knowledge_base",
    }
