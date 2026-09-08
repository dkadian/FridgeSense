from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, status

from ..deps import current_user, get_conn, get_kn
from ..knowledge import Knowledge
from ..schemas import ImageParseRequest, ReceiptConfirmRequest, ReceiptParseRequest
from ..services import llm_service, receipt_service

router = APIRouter(prefix="/api/receipt", tags=["receipt"])


@router.post("/parse", summary="Read a pasted receipt without saving anything")
def parse(payload: ReceiptParseRequest, user: dict = Depends(current_user),
          kn: Knowledge = Depends(get_kn)):
    return receipt_service.parse_receipt(payload.text, kn, payload.purchase_date)


@router.post("/parse-text", summary="Parse unstructured Hinglish text / WhatsApp notes into pantry candidates")
def parse_text(payload: ReceiptParseRequest, user: dict = Depends(current_user),
               kn: Knowledge = Depends(get_kn)):
    return llm_service.parse_hinglish_grocery_text(payload.text, kn, payload.purchase_date)


@router.post("/parse-image", summary="Multimodal vision inspection of grocery receipts or fridge shelves")
def parse_image(payload: ImageParseRequest, user: dict = Depends(current_user),
                kn: Knowledge = Depends(get_kn)):
    return llm_service.parse_vision_image(
        image_base64=payload.image_base64,
        mime_type=payload.mime_type,
        mode=payload.mode,
        kn=kn,
        purchase_date=payload.purchase_date,
    )


@router.post("/confirm", status_code=status.HTTP_201_CREATED,
             summary="Commit a reviewed receipt into the pantry")
def confirm(payload: ReceiptConfirmRequest, user: dict = Depends(current_user),
            conn: sqlite3.Connection = Depends(get_conn),
            kn: Knowledge = Depends(get_kn)):
    return receipt_service.confirm(
        conn, user["id"], [i.model_dump() for i in payload.items], kn)

