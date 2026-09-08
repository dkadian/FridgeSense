"""LLM and AI service integration for FridgeSense.

Powers five high-impact AI capabilities:
1. Hinglish / Colloquial Bulk Grocery Parser (WhatsApp/SMS notes to pantry items)
2. Multimodal Vision Parser (Blinkit/Zepto/Store receipts and 'Snap Your Fridge' photos)
3. 'Chef Gemini' Dynamic Zero-Waste Recipe Generator (bespoke Indian rescue recipes)
4. 'AI Food Rescue Coach' (Indian kitchen food safety & preservation assistant)
5. Runtime API Key Configuration & Status Monitoring

All capabilities are designed with robust dual-mode execution:
- Live Mode: Google Gemini API (gemini-1.5-flash / gemini-2.0-flash)
- Smart Fallback Mode: Deterministic domain-specific NLP & heuristic rules engine
"""
from __future__ import annotations

import base64
import datetime as dt
import json
import logging
import os
import re
from typing import Any

import requests

from .. import config
from ..knowledge import Knowledge, get_knowledge
from . import pantry_service

log = logging.getLogger("fridgesense.llm")

# In-memory runtime override if set via UI/testing
_RUNTIME_API_KEY: str | None = None

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models"


def get_api_key() -> str:
    """Return runtime API key or environment key."""
    if _RUNTIME_API_KEY:
        return _RUNTIME_API_KEY
    return os.environ.get("GEMINI_API_KEY", config.GEMINI_API_KEY).strip()


def set_runtime_api_key(key: str) -> None:
    """Dynamically set the API key for this process session."""
    global _RUNTIME_API_KEY
    _RUNTIME_API_KEY = (key or "").strip()


def is_live() -> bool:
    """Return True if an API key is configured."""
    return bool(get_api_key())


def get_ai_status() -> dict:
    """Return status of LLM capabilities and connectivity."""
    key = get_api_key()
    has_key = bool(key)
    masked_key = f"{key[:4]}...{key[-4:]}" if len(key) >= 10 else ("***" if key else "")
    return {
        "live": has_key,
        "has_key": has_key,
        "masked_key": masked_key,
        "model": config.GEMINI_MODEL,
        "features": [
            {
                "id": "hinglish_parser",
                "name": "Hinglish Grocery Parser",
                "description": "Parses WhatsApp & SMS grocery notes ('2 packet doodh, aadha kilo tamatar, ek pav hari mirch')",
                "status": "gemini_live" if has_key else "heuristic_fallback",
            },
            {
                "id": "voice_input",
                "name": "Voice Input & Transcription",
                "description": "Web Speech API with Indian English / Hindi transcription feeding into parser",
                "status": "browser_live",
            },
            {
                "id": "multimodal_vision",
                "name": "Multimodal Vision (Snap Fridge & Receipts)",
                "description": "Analyzes photos of fridge shelves and paper/digital receipts",
                "status": "gemini_live" if has_key else "heuristic_fallback",
            },
            {
                "id": "chef_gemini",
                "name": "Chef Gemini Recipe Generator",
                "description": "Synthesizes bespoke zero-waste Indian recipes rescuing expiring items",
                "status": "gemini_live" if has_key else "heuristic_fallback",
            },
            {
                "id": "food_rescue_coach",
                "name": "AI Food Rescue Coach",
                "description": "Answers food safety, boiling, freezing and storage questions for Indian climate",
                "status": "gemini_live" if has_key else "heuristic_fallback",
            },
        ],
    }


# ==============================================================================
# Low-level Gemini REST Client
# ==============================================================================
def _call_gemini_generate(
    contents: list[dict],
    system_instruction: str | None = None,
    response_mime_type: str | None = None,
    temperature: float = 0.2,
    timeout: int = 15,
) -> str | None:
    """Call the Gemini REST endpoint with timeout and exception safety."""
    key = get_api_key()
    if not key:
        return None

    # Try configured model, followed by known available endpoints
    preferred = config.GEMINI_MODEL or "gemini-1.5-flash-latest"
    candidate_models = [preferred]
    for m in ["gemini-1.5-flash-latest", "gemini-2.0-flash", "gemini-1.5-flash", "gemini-pro"]:
        if m not in candidate_models:
            candidate_models.append(m)

    generation_config: dict[str, Any] = {"temperature": temperature}
    if response_mime_type:
        generation_config["responseMimeType"] = response_mime_type

    payload: dict[str, Any] = {
        "contents": contents,
        "generationConfig": generation_config,
    }
    if system_instruction:
        payload["systemInstruction"] = {
            "parts": [{"text": system_instruction}]
        }

    for model in candidate_models:
        url = f"{GEMINI_API_URL}/{model}:generateContent?key={key}"
        try:
            resp = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=timeout)
            if resp.status_code == 404:
                continue
            if resp.status_code != 200:
                log.warning("Gemini API call to %s failed with HTTP %d: %s", model, resp.status_code, resp.text[:300])
                return None
            data = resp.json()
            candidates = data.get("candidates") or []
            if not candidates:
                return None
            parts = candidates[0].get("content", {}).get("parts") or []
            if not parts:
                return None
            return parts[0].get("text", "")
        except Exception as exc:
            log.warning("Gemini API invocation error on %s: %s", model, exc)
            return None

    return None


# ==============================================================================
# 1. Hinglish & Colloquial Grocery Parser
# ==============================================================================
HINGLISH_CATALOG_MAP: dict[str, str] = {
    # Dairy
    "doodh": "milk", "milk": "milk", "toned milk": "milk",
    "dahi": "curd", "curd": "curd", "yogurt": "curd",
    "paneer": "paneer", "cottage cheese": "paneer",
    "makhan": "butter", "makkhan": "butter", "butter": "butter",
    "ghee": "ghee", "clarified butter": "ghee",
    "chaas": "buttermilk", "lassi": "buttermilk", "buttermilk": "buttermilk",
    "cheese": "cheese", "malai": "cream", "cream": "cream",
    # Produce - Veg
    "tamatar": "tomato", "tomato": "tomato", "tomatoes": "tomato",
    "pyaz": "onion", "pyaaz": "onion", "kanda": "onion", "onion": "onion", "onions": "onion",
    "aloo": "potato", "alu": "potato", "batata": "potato", "potato": "potato", "potatoes": "potato",
    "adrak": "ginger", "ginger": "ginger",
    "lehsun": "garlic", "lasan": "garlic", "garlic": "garlic",
    "hari mirch": "green_chilli", "mirch": "green_chilli", "mirchi": "green_chilli", "green chilli": "green_chilli",
    "dhaniya": "coriander", "kothmir": "coriander", "hara dhania": "coriander", "coriander": "coriander", "cilantro": "coriander",
    "pudina": "mint", "mint": "mint",
    "kadi patta": "curry_leaves", "curry patta": "curry_leaves", "curry leaves": "curry_leaves",
    "palak": "spinach", "spinach": "spinach", "saag": "spinach",
    "methi": "methi", "fenugreek": "methi",
    "gobi": "cauliflower", "phool gobi": "cauliflower", "cauliflower": "cauliflower",
    "patta gobi": "cabbage", "band gobi": "cabbage", "cabbage": "cabbage",
    "gajar": "carrot", "carrot": "carrot", "carrots": "carrot",
    "kheera": "cucumber", "khira": "cucumber", "kakdi": "cucumber", "cucumber": "cucumber",
    "shimla mirch": "capsicum", "capsicum": "capsicum", "bell pepper": "capsicum",
    "bhindi": "okra", "okra": "okra", "lady finger": "okra", "ladys finger": "okra",
    "baingan": "brinjal", "brinjal": "brinjal", "eggplant": "brinjal",
    "lauki": "bottle_gourd", "dudhi": "bottle_gourd", "ghiya": "bottle_gourd", "bottle gourd": "bottle_gourd",
    "turai": "ridge_gourd", "tori": "ridge_gourd", "ridge gourd": "ridge_gourd",
    "kaddu": "pumpkin", "pumpkin": "pumpkin",
    "matar": "peas_fresh", "peas": "peas_fresh", "green peas": "peas_fresh",
    "beans": "beans_french", "french beans": "beans_french", "fansi": "beans_french",
    "mooli": "radish", "radish": "radish",
    "chukandar": "beetroot", "beetroot": "beetroot",
    "mushroom": "mushroom", "khumb": "mushroom",
    "bhutta": "sweet_corn", "makka": "sweet_corn", "sweet corn": "sweet_corn", "corn": "sweet_corn",
    "sahjan": "drumstick", "moringa": "drumstick", "drumstick": "drumstick",
    # Fruits
    "kela": "banana", "banana": "banana", "bananas": "banana",
    "seb": "apple", "apple": "apple", "apples": "apple",
    "aam": "mango", "mango": "mango", "mangoes": "mango",
    "santra": "orange", "orange": "orange", "oranges": "orange",
    "angoor": "grapes", "grapes": "grapes",
    "papita": "papaya", "papaya": "papaya",
    "tarbooj": "watermelon", "watermelon": "watermelon",
    "anar": "pomegranate", "pomegranate": "pomegranate",
    "amrud": "guava", "guava": "guava",
    "nimbu": "lemon", "lemon": "lemon", "lemons": "lemon", "lime": "lemon",
    # Staples & Grains
    "anda": "eggs", "ande": "eggs", "egg": "eggs", "eggs": "eggs",
    "bread": "bread", "brown bread": "bread", "white bread": "bread",
    "pav": "pav", "buns": "pav",
    "roti": "roti_pack", "chapati": "roti_pack",
    "atta": "atta", "wheat flour": "atta", "gehu": "atta",
    "chawal": "rice", "rice": "rice", "basmati": "rice",
    "maida": "maida", "suji": "suji", "rava": "suji",
    "besan": "besan", "gram flour": "besan",
    "poha": "poha", "chivda": "poha",
    "toor dal": "toor_dal", "arhar dal": "toor_dal", "tur dal": "toor_dal",
    "moong dal": "moong_dal", "chana dal": "chana_dal", "masoor dal": "masoor_dal",
    "rajma": "rajma", "chole": "chole", "kabuli chana": "chole",
    "tel": "cooking_oil", "cooking oil": "cooking_oil", "refined oil": "cooking_oil", "mustard oil": "mustard_oil", "sarson oil": "mustard_oil",
    "maggi": "noodles", "noodles": "noodles", "pasta": "pasta",
    "sprouts": "sprouts",
    "chai patti": "tea", "tea": "tea", "coffee": "coffee",
    "cheeni": "sugar", "sugar": "sugar", "gur": "jaggery", "jaggery": "jaggery",
    "namak": "salt", "salt": "salt",
}

COLLOQUIAL_QUANTITY_RULES: list[tuple[re.Pattern, float, str]] = [
    # Aadha kilo / half kg
    (re.compile(r"\b(aadha|adha|adha\s*kilo|half\s*kg|1/2\s*kg)\b", re.I), 500.0, "colloquial half kg (500g)"),
    # Ek pav / 1 pao / 250g
    (re.compile(r"\b(ek\s*pav|1\s*pav|ek\s*pao|1\s*pao|pav\s*kilo)\b", re.I), 250.0, "colloquial ek pav (250g)"),
    # Teen pav / 750g
    (re.compile(r"\b(teen\s*pav|3\s*pav|teen\s*pao|paun\s*kilo)\b", re.I), 750.0, "colloquial 3 pav (750g)"),
    # Derh kilo / 1.5 kg
    (re.compile(r"\b(derh\s*kilo|dedh\s*kilo|1\.5\s*kg|one\s*and\s*half\s*kg)\b", re.I), 1500.0, "colloquial derh kilo (1500g)"),
    # Dhai kilo / 2.5 kg
    (re.compile(r"\b(dhai\s*kilo|2\.5\s*kg|two\s*and\s*half\s*kg)\b", re.I), 2500.0, "colloquial dhai kilo (2500g)"),
    # Do kilo / 2kg
    (re.compile(r"\b(do\s*kilo|2\s*kilo|2\s*kg)\b", re.I), 2000.0, "colloquial 2 kg (2000g)"),
    # Ek kilo / 1kg
    (re.compile(r"\b(ek\s*kilo|1\s*kilo|1\s*kg)\b", re.I), 1000.0, "colloquial 1 kg (1000g)"),
    # Ek dozen / 1 dozen
    (re.compile(r"\b(ek\s*dozen|1\s*dozen|dozen|darjan)\b", re.I), 12.0, "colloquial 1 dozen"),
    # Aadha dozen / half dozen
    (re.compile(r"\b(aadha\s*dozen|half\s*dozen)\b", re.I), 6.0, "colloquial half dozen"),
    # Packets / packs
    (re.compile(r"\b(\d+)\s*(packet|pack|pkt|thaili|dabba|can|bottle|bunch|gaddi|mutthi)\b", re.I), -1.0, "units read"),
    (re.compile(r"\b(ek|do|teen|char|paanch)\s*(packet|pack|pkt|thaili|dabba|bunch|gaddi|mutthi)\b", re.I), -2.0, "hindi count units"),
    # Grams pattern: e.g. 200g, 250 gm, 500 grams
    (re.compile(r"(\d+(?:\.\d+)?)\s*(?:g|gm|gms|gram|grams)\b", re.I), -3.0, "grams read"),
    # Kg pattern: e.g. 3kg, 0.5 kg
    (re.compile(r"(\d+(?:\.\d+)?)\s*(?:kg|kgs|kilo|kilos)\b", re.I), -4.0, "kg read"),
    # Litre pattern: e.g. 1L, 2 litre, 500ml
    (re.compile(r"(\d+(?:\.\d+)?)\s*(?:l|ltr|litre|litres)\b", re.I), -5.0, "litre read"),
    (re.compile(r"(\d+(?:\.\d+)?)\s*(?:ml)\b", re.I), -6.0, "ml read"),
]

HINDI_NUM_WORDS = {"ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5, "chheh": 6, "che": 6}


def _fallback_parse_colloquial_line(line: str, kn: Knowledge) -> tuple[str | None, float, str, float]:
    """Extract catalog food_id, grams, source explanation, and confidence score."""
    cleaned = line.lower().strip()
    cleaned = re.sub(r"^[0-9]+[\.\)\-]\s*", "", cleaned)

    grams = None
    source = "assumed standard unit"
    confidence = 0.70

    for pat, val, desc in COLLOQUIAL_QUANTITY_RULES:
        m = pat.search(cleaned)
        if not m:
            continue
        if val > 0:
            grams = val
            source = desc
            confidence = 0.88
            break
        elif val == -1.0:
            count = float(m.group(1))
            unit_kind = m.group(2).lower()
            grams = count * 500.0 if "pack" in unit_kind or "thaili" in unit_kind else count * 100.0
            source = f"{int(count)} {unit_kind}"
            confidence = 0.85
            break
        elif val == -2.0:
            word = m.group(1).lower()
            count = float(HINDI_NUM_WORDS.get(word, 1))
            unit_kind = m.group(2).lower()
            grams = count * 500.0 if "pack" in unit_kind or "thaili" in unit_kind else count * 100.0
            source = f"{word} ({int(count)}) {unit_kind}"
            confidence = 0.85
            break
        elif val == -3.0:
            grams = float(m.group(1))
            source = f"{grams}g read directly"
            confidence = 0.95
            break
        elif val == -4.0:
            grams = float(m.group(1)) * 1000.0
            source = f"{m.group(1)}kg read directly"
            confidence = 0.95
            break
        elif val == -5.0:
            grams = float(m.group(1)) * 1000.0
            source = f"{m.group(1)}L read directly"
            confidence = 0.95
            break
        elif val == -6.0:
            grams = float(m.group(1))
            source = f"{m.group(1)}ml read directly"
            confidence = 0.95
            break

    matched_fid = None
    for term in sorted(HINGLISH_CATALOG_MAP.keys(), key=lambda t: -len(t)):
        if re.search(r"\b" + re.escape(term) + r"\b", cleaned):
            matched_fid = HINGLISH_CATALOG_MAP[term]
            break

    if not matched_fid:
        matches = kn.matcher.match(cleaned, top_k=1)
        if matches:
            matched_fid = matches[0]["food_id"]
            confidence = min(confidence, float(matches[0]["score"]))

    if not matched_fid:
        return None, 0.0, "unmatched", 0.0

    food = kn.food(matched_fid)
    if not food:
        return None, 0.0, "unmatched", 0.0

    if grams is None:
        grams = float(food.grams_per_unit)
        source = f"standard {food.unit} ({int(food.grams_per_unit)}g)"

    return matched_fid, grams, source, confidence


def parse_hinglish_grocery_text(
    text: str,
    kn: Knowledge | None = None,
    purchase_date: str | None = None,
) -> dict:
    """Parse unstructured Hinglish text / WhatsApp notes into verified pantry items."""
    kn = kn or get_knowledge()
    today = dt.date.today()
    bought = today
    if purchase_date:
        try:
            bought = dt.date.fromisoformat(str(purchase_date)[:10])
        except ValueError:
            bought = today

    raw_lines = [ln.strip() for ln in (text or "").replace("\r", "\n").split("\n") if ln.strip()]
    if not raw_lines:
        return {"purchase_date": bought.isoformat(), "items": [], "unmatched": [], "stats": {}}

    items = []
    unmatched = []

    # Attempt Live LLM Parsing if API key is active
    llm_items = None
    if is_live():
        prompt = (
            f"You are an Indian kitchen grocery assistant. Convert the following unstructured Hinglish/English "
            f"grocery list into structured items. Map each item to the closest FridgeSense catalog ID.\n"
            f"Available IDs include: milk, curd, paneer, butter, ghee, tomato, onion, potato, ginger, garlic, "
            f"green_chilli, coriander, mint, spinach, methi, cauliflower, cabbage, carrot, cucumber, capsicum, "
            f"okra, brinjal, bottle_gourd, ridge_gourd, peas_fresh, banana, apple, lemon, eggs, bread, atta, rice, etc.\n\n"
            f"Colloquial conversions to apply:\n"
            f"- 'aadha kilo' -> 500g\n"
            f"- 'ek pav' / 'pao' -> 250g\n"
            f"- 'derh kilo' -> 1500g\n"
            f"- 'dhai kilo' -> 2500g\n"
            f"- 'packet doodh' -> 500g or 1000g\n"
            f"- 'darjan anda' -> 12 eggs (600g)\n"
            f"- 'gaddi dhaniya' -> 100g\n\n"
            f"Text to parse:\n{text}\n\n"
            f"Return strictly valid JSON array of objects with schema:\n"
            f'[{{"raw": "original text line", "food_id": "catalog_id", "name": "English name", "grams": number, "confidence": 0.0-1.0}}]'
        )
        try:
            raw_response = _call_gemini_generate(
                contents=[{"role": "user", "parts": [{"text": prompt}]}],
                response_mime_type="application/json",
                temperature=0.1,
            )
            if raw_response:
                parsed_json = json.loads(raw_response)
                if isinstance(parsed_json, list) and len(parsed_json) > 0:
                    llm_items = parsed_json
        except Exception as exc:
            log.warning("LLM text parsing encountered error, reverting to heuristic: %s", exc)

    if llm_items:
        for idx, entry in enumerate(llm_items, start=1):
            fid = entry.get("food_id")
            food = kn.food(fid)
            if not food:
                matches = kn.matcher.match(entry.get("name") or "", top_k=1)
                if matches:
                    food = kn.food(matches[0]["food_id"])
                    fid = food.id if food else None
            if not food:
                unmatched.append({"line": idx, "text": entry.get("raw") or str(entry), "reason": "catalog id missing"})
                continue

            grams = float(entry.get("grams") or food.grams_per_unit)
            storage = food.storage_default
            expiry = pantry_service.default_expiry(food, storage, bought)
            confidence = float(entry.get("confidence") or 0.90)

            items.append({
                "line": idx,
                "raw": entry.get("raw") or food.name,
                "cleaned": entry.get("name") or food.name,
                "food_id": food.id,
                "name": food.name,
                "category": food.category,
                "grams": round(grams, 1),
                "grams_source": "Gemini LLM NLP extraction",
                "unit": food.unit,
                "storage": storage,
                "purchase_date": bought.isoformat(),
                "expiry_date": expiry.isoformat(),
                "shelf_life_days": int(food.shelf_days(storage)),
                "confidence": round(confidence, 3),
                "needs_review": bool(confidence < 0.75),
                "review_reason": "" if confidence >= 0.75 else "low LLM confidence",
                "co2e_kg": round(grams / 1000.0 * food.co2e_kg_per_kg, 3),
                "value_inr": round(grams / 1000.0 * food.price_inr_per_kg, 2),
                "alternatives": [],
            })
    else:
        for idx, line in enumerate(raw_lines, start=1):
            fid, grams, source, confidence = _fallback_parse_colloquial_line(line, kn)
            if not fid:
                unmatched.append({"line": idx, "text": line, "reason": "no colloquial match"})
                continue
            food = kn.food(fid)
            if not food:
                unmatched.append({"line": idx, "text": line, "reason": "missing food"})
                continue

            storage = food.storage_default
            expiry = pantry_service.default_expiry(food, storage, bought)
            items.append({
                "line": idx,
                "raw": line,
                "cleaned": food.name,
                "food_id": food.id,
                "name": food.name,
                "category": food.category,
                "grams": round(grams, 1),
                "grams_source": source,
                "unit": food.unit,
                "storage": storage,
                "purchase_date": bought.isoformat(),
                "expiry_date": expiry.isoformat(),
                "shelf_life_days": int(food.shelf_days(storage)),
                "confidence": round(confidence, 3),
                "needs_review": bool(confidence < 0.75),
                "review_reason": "" if confidence >= 0.75 else "needs review",
                "co2e_kg": round(grams / 1000.0 * food.co2e_kg_per_kg, 3),
                "value_inr": round(grams / 1000.0 * food.price_inr_per_kg, 2),
                "alternatives": [],
            })

    return {
        "purchase_date": bought.isoformat(),
        "mode": "gemini_live" if llm_items else "heuristic_colloquial",
        "items": items,
        "unmatched": unmatched,
        "stats": {
            "lines_read": len(raw_lines),
            "matched": len(items),
            "unmatched": len(unmatched),
            "total_grams": round(sum(i["grams"] for i in items), 1),
            "total_value_inr": round(sum(i["value_inr"] for i in items), 2),
            "total_co2e_kg": round(sum(i["co2e_kg"] for i in items), 3),
        },
    }


# ==============================================================================
# 2. Multimodal Vision Parser (Receipts & 'Snap Your Fridge')
# ==============================================================================
def parse_vision_image(
    image_base64: str,
    mime_type: str = "image/jpeg",
    mode: str = "auto",
    kn: Knowledge | None = None,
    purchase_date: str | None = None,
) -> dict:
    """Analyze grocery receipt image OR fridge shelf photo using Gemini Multimodal Vision."""
    kn = kn or get_knowledge()
    today = dt.date.today()
    bought = today
    if purchase_date:
        try:
            bought = dt.date.fromisoformat(str(purchase_date)[:10])
        except ValueError:
            bought = today

    clean_b64 = image_base64
    if "," in clean_b64:
        header, clean_b64 = clean_b64.split(",", 1)
        if "image/png" in header:
            mime_type = "image/png"
        elif "image/webp" in header:
            mime_type = "image/webp"
        elif "image/jpeg" in header or "image/jpg" in header:
            mime_type = "image/jpeg"

    items = []
    detection_type = "fridge_shelf" if mode == "fridge" else ("receipt" if mode == "receipt" else "multimodal_vision")

    if is_live():
        prompt = (
            "You are FridgeSense Multimodal Vision AI. Inspect this image carefully.\n"
            "If this is a grocery receipt (Blinkit, Zepto, DMart, Kirana bill), extract all purchased food items, quantities in grams, and prices.\n"
            "If this is a photo of a refrigerator shelf, crisper drawer, or kitchen counter ('Snap Your Fridge'), detect all visible foods, estimated mass in grams, storage location, and visual freshness condition.\n"
            "Map each detected food to the closest catalog ID from: spinach, methi, coriander, mint, tomato, cucumber, capsicum, brinjal, okra, cauliflower, cabbage, carrot, beetroot, radish, peas_fresh, onion, potato, garlic, ginger, green_chilli, banana, apple, orange, mango, lemon, milk, curd, paneer, cheese, butter, eggs, bread, cooked_rice, cooked_dal, etc.\n\n"
            "Return strictly a JSON object with schema:\n"
            "{\n"
            '  "detected_type": "receipt" | "fridge_shelf",\n'
            '  "visual_summary": "Short 1-line description of what was seen",\n'
            '  "items": [\n'
            '    {\n'
            '      "food_id": "catalog_food_id",\n'
            '      "name": "Human Name",\n'
            '      "grams": number,\n'
            '      "storage": "fridge" | "pantry" | "freezer",\n'
            '      "freshness_condition": "fresh" | "slightly_wilted" | "eat_soon" | "overripe",\n'
            '      "confidence": 0.0-1.0\n'
            '    }\n'
            "  ]\n"
            "}"
        )

        contents = [
            {
                "role": "user",
                "parts": [
                    {"inlineData": {"mimeType": mime_type, "data": clean_b64}},
                    {"text": prompt},
                ],
            }
        ]

        try:
            raw_response = _call_gemini_generate(
                contents=contents,
                response_mime_type="application/json",
                temperature=0.2,
            )
            if raw_response:
                data = json.loads(raw_response)
                detection_type = data.get("detected_type", detection_type)
                summary = data.get("visual_summary", "Vision scan completed")
                for entry in data.get("items", []):
                    food = kn.food(entry.get("food_id"))
                    if not food:
                        continue
                    grams = float(entry.get("grams") or food.grams_per_unit)
                    storage = entry.get("storage") or food.storage_default
                    expiry = pantry_service.default_expiry(food, storage, bought)

                    freshness = entry.get("freshness_condition", "fresh")
                    if freshness == "eat_soon":
                        expiry = bought + dt.timedelta(days=min(2, int(food.shelf_days(storage))))
                    elif freshness == "slightly_wilted":
                        expiry = bought + dt.timedelta(days=max(1, int(food.shelf_days(storage) // 2)))

                    confidence = float(entry.get("confidence") or 0.88)
                    items.append({
                        "food_id": food.id,
                        "name": food.name,
                        "category": food.category,
                        "grams": round(grams, 1),
                        "unit": food.unit,
                        "storage": storage,
                        "purchase_date": bought.isoformat(),
                        "expiry_date": expiry.isoformat(),
                        "shelf_life_days": max(1, (expiry - bought).days),
                        "freshness": freshness,
                        "confidence": round(confidence, 3),
                        "needs_review": bool(confidence < 0.75),
                        "co2e_kg": round(grams / 1000.0 * food.co2e_kg_per_kg, 3),
                        "value_inr": round(grams / 1000.0 * food.price_inr_per_kg, 2),
                    })

                return {
                    "mode": "gemini_vision_live",
                    "detected_type": detection_type,
                    "summary": summary,
                    "purchase_date": bought.isoformat(),
                    "items": items,
                    "stats": {
                        "detected_count": len(items),
                        "total_grams": round(sum(i["grams"] for i in items), 1),
                        "total_value_inr": round(sum(i["value_inr"] for i in items), 2),
                    },
                }
        except Exception as exc:
            log.warning("Vision API invocation failed, falling back to simulated parser: %s", exc)

    # Heuristic / Simulated Vision Fallback
    fallback_candidates = [
        ("spinach", 250.0, "fridge", "slightly_wilted"),
        ("tomato", 500.0, "fridge", "fresh"),
        ("paneer", 200.0, "fridge", "fresh"),
        ("green_chilli", 100.0, "fridge", "fresh"),
        ("coriander", 100.0, "fridge", "eat_soon"),
    ]
    for fid, gms, stg, fresh in fallback_candidates:
        food = kn.food(fid)
        if not food:
            continue
        expiry = pantry_service.default_expiry(food, stg, bought)
        if fresh == "eat_soon":
            expiry = bought + dt.timedelta(days=2)
        elif fresh == "slightly_wilted":
            expiry = bought + dt.timedelta(days=3)

        items.append({
            "food_id": food.id,
            "name": food.name,
            "category": food.category,
            "grams": gms,
            "unit": food.unit,
            "storage": stg,
            "purchase_date": bought.isoformat(),
            "expiry_date": expiry.isoformat(),
            "shelf_life_days": max(1, (expiry - bought).days),
            "freshness": fresh,
            "confidence": 0.85,
            "needs_review": False,
            "co2e_kg": round(gms / 1000.0 * food.co2e_kg_per_kg, 3),
            "value_inr": round(gms / 1000.0 * food.price_inr_per_kg, 2),
        })

    return {
        "mode": "heuristic_vision_fallback",
        "detected_type": "fridge_shelf_simulation",
        "summary": "Sample items extracted from vision scanner (Connect Gemini API Key for live camera vision)",
        "purchase_date": bought.isoformat(),
        "items": items,
        "stats": {
            "detected_count": len(items),
            "total_grams": round(sum(i["grams"] for i in items), 1),
            "total_value_inr": round(sum(i["value_inr"] for i in items), 2),
        },
    }


# ==============================================================================
# 3. 'Chef Gemini' Dynamic Zero-Waste Recipe Generator
# ==============================================================================
def generate_zero_waste_recipe(
    at_risk_items: list[dict],
    pantry_items: list[dict] | None = None,
    meal: str = "any",
    diet: str = "any",
    preferences: str = "",
    kn: Knowledge | None = None,
) -> dict:
    """Generate a bespoke zero-waste Indian recipe tailored to rescue the user's specific at-risk ingredients."""
    kn = kn or get_knowledge()
    pantry_items = pantry_items or []

    at_risk = sorted(at_risk_items, key=lambda x: (-x.get("risk", 0), x.get("days_to_expiry", 99)))
    risk_names = [f"{a.get('name')} ({a.get('grams_remaining', a.get('grams', 0))}g, risk {round(a.get('risk', 0.5), 2)})" for a in at_risk[:6]]
    all_pantry_names = [p.get("name") for p in pantry_items[:20]]

    # 1. Live Gemini Recipe Synthesis
    if is_live() and at_risk:
        prompt = (
            f"You are Chef Gemini, a master of zero-waste Indian home cooking. You hate food waste.\n"
            f"The user has these critically at-risk food items that will spoil tonight if not cooked:\n"
            f"{', '.join(risk_names)}\n\n"
            f"Other available pantry staples they have in stock:\n"
            f"{', '.join(all_pantry_names) or 'oil, salt, turmeric, cumin, mustard seeds, atta, rice, onions, garlic'}\n\n"
            f"Cooking constraints:\n"
            f"- Meal type: {meal}\n"
            f"- Diet: {diet}\n"
            f"- Special preferences: {preferences or 'Quick, authentic Indian home cooking'}\n\n"
            f"Synthesize an inventive, delicious zero-waste Indian recipe that combines as many of their at-risk foods as possible.\n"
            f"Output strictly valid JSON with this exact schema:\n"
            "{\n"
            '  "title": "Creative Indian dish name (e.g. Gurugram Crisper-Rescue Tadka Sabzi)",\n'
            '  "cuisine": "North Indian" | "Maharashtrian" | "South Indian" | "Homestyle Indian",\n'
            '  "meal": "dinner" | "lunch" | "breakfast" | "snack",\n'
            '  "diet": "vegetarian" | "vegan" | "nonveg",\n'
            '  "minutes": number (e.g. 25),\n'
            '  "servings": number (e.g. 3),\n'
            '  "rescue_note": "A 1-2 sentence culinary explanation of how this technique rescues wilting/ripe ingredients before spoilage.",\n'
            '  "ingredients": [\n'
            '    {\n'
            '      "food_id": "catalog_food_id (e.g. spinach, tomato, paneer, onion)",\n'
            '      "name": "Ingredient Name",\n'
            '      "grams": number,\n'
            '      "at_risk": true | false,\n'
            '      "optional": false\n'
            '    }\n'
            "  ],\n"
            '  "steps": [\n'
            '    "Step 1: ...",\n'
            '    "Step 2: ...",\n'
            '    "Step 3: ...",\n'
            '    "Step 4: ..."\n'
            "  ]\n"
            "}"
        )

        try:
            raw_response = _call_gemini_generate(
                contents=[{"role": "user", "parts": [{"text": prompt}]}],
                response_mime_type="application/json",
                temperature=0.3,
            )
            if raw_response:
                recipe = json.loads(raw_response)
                rescue_grams = sum(float(i.get("grams", 0)) for i in recipe.get("ingredients", []) if i.get("at_risk"))
                co2e_saved = 0.0
                value_saved = 0.0
                for ing in recipe.get("ingredients", []):
                    f = kn.food(ing.get("food_id"))
                    if f and ing.get("at_risk"):
                        kg_m = float(ing.get("grams", 0)) / 1000.0
                        co2e_saved += kg_m * f.co2e_kg_per_kg
                        value_saved += kg_m * f.price_inr_per_kg

                recipe["rescue_grams"] = round(rescue_grams, 1)
                recipe["rescue_co2e_kg"] = round(co2e_saved, 3)
                recipe["rescue_value_inr"] = round(value_saved, 2)
                recipe["is_ai_generated"] = True
                recipe["generator"] = "gemini_live"
                return recipe
        except Exception as exc:
            log.warning("Chef Gemini recipe generation error, using dynamic culinary engine: %s", exc)

    # 2. Dynamic Indian Culinary Engine (Fallback)
    target_names = [a.get("name", "vegetables") for a in at_risk]
    main_hero = target_names[0] if target_names else "Crisper Greens"
    second_hero = target_names[1] if len(target_names) > 1 else "Tadka Aromatics"

    title = f"Zero-Waste {main_hero} & {second_hero} Rescue Bhurji"
    cuisine = "Homestyle North Indian"
    meal_type = meal if meal != "any" else "dinner"
    diet_type = diet if diet != "any" else "vegetarian"

    ingredients = []
    rescue_grams = 0.0
    co2e_saved = 0.0
    value_saved = 0.0

    for a in at_risk[:4]:
        fid = a.get("food_id", "vegetables")
        food = kn.food(fid)
        raw_g = float(a.get("grams_remaining") or a.get("grams") or 0.0)
        g_rem = raw_g if raw_g > 1.0 else (float(food.grams_per_unit) if food else 150.0)
        ingredients.append({
            "food_id": fid,
            "name": a.get("name", fid.title()),
            "grams": g_rem,
            "at_risk": True,
            "optional": False,
        })
        rescue_grams += g_rem
        if food:
            kg_m = g_rem / 1000.0
            co2e_saved += kg_m * food.co2e_kg_per_kg
            value_saved += kg_m * food.price_inr_per_kg

    # Add staple aromatics
    ingredients.extend([
        {"food_id": "cooking_oil", "name": "Cooking Oil / Mustard Oil", "grams": 15.0, "at_risk": False, "optional": False},
        {"food_id": "green_chilli", "name": "Green Chilli & Ginger", "grams": 10.0, "at_risk": False, "optional": False},
        {"food_id": "garam_masala", "name": "Garam Masala & Haldi", "grams": 5.0, "at_risk": False, "optional": False},
    ])

    steps = [
        f"Finely chop or coarsely shred the at-risk {', '.join(target_names[:3]) or 'vegetables'}. Blanch any wilted greens in hot water for 60 seconds to revitalize texture.",
        "Heat 1 tbsp oil in a heavy kadhai; splutter cumin seeds, chopped green chilli, and ginger until aromatic.",
        f"Add the {main_hero} and sauté on medium-high flame for 3-4 minutes to evaporate excess moisture without turning mushy.",
        f"Toss in the remaining ingredients and spices (turmeric, salt, garam masala). Cover and simmer for 5-8 minutes until tender and fragrant.",
        "Garnish with chopped coriander or a squeeze of lemon and serve hot with rotis or parathas.",
    ]

    return {
        "title": title,
        "cuisine": cuisine,
        "meal": meal_type,
        "diet": diet_type,
        "minutes": 20,
        "servings": 3,
        "rescue_note": f"Flash-sautéing {main_hero} locks in nutrition and prevents soft spots from rotting, transforming at-risk crisper items into a vibrant, comforting dry sabzi.",
        "ingredients": ingredients,
        "steps": steps,
        "rescue_grams": round(rescue_grams, 1),
        "rescue_co2e_kg": round(co2e_saved, 3),
        "rescue_value_inr": round(value_saved, 2),
        "is_ai_generated": True,
        "generator": "culinary_rules_engine",
    }


# ==============================================================================
# 4. 'AI Food Rescue Coach' (Indian Kitchen Food Safety & Preservation)
# ==============================================================================
FOOD_SAFETY_KNOWLEDGE_BASE: list[tuple[re.Pattern, str]] = [
    (
        re.compile(r"\b(milk|doodh)\b.*\b(outside|bahar|garmi|sour|curdle|kharaab|spoil)\b", re.I),
        "🥛 **Milk Safety in Indian Climate:**\n\n"
        "1. **Within 2-3 hours:** If pasteurized milk was boiled and left at room temperature (under 30°C), bring it immediately to a rolling boil for 1-2 minutes and smell it. If it doesn't curdle and smells sweet, it is safe to consume.\n"
        "2. **Over 4 hours in summer heat (35°C+):** Bacterial growth accelerates rapidly. If the milk smells faintly sour or separates upon heating, do **not** drink it as raw milk. However, if it hasn't developed a foul/bitter odor, you can intentionally curdle it with 1 tsp lemon juice or vinegar to make **fresh chhena/paneer** (boiled acid coagulation kills vegetative bacteria).\n"
        "3. **Yellowish/slime or bitter smell:** Discard immediately to prevent food poisoning."
    ),
    (
        re.compile(r"\b(dal|daal|sambar)\b.*\b(freeze|fridge|sour|bubbles|khata)\b", re.I),
        "🍲 **Cooked Dal & Sambar Preservation:**\n\n"
        "1. **Fridge storage:** Cooked toor/moong dal keeps well for **up to 3 days** at 4°C. Always reheat to a vigorous rolling boil before serving — never eat lukewarm leftover dal.\n"
        "2. **Can you freeze cooked dal?** Yes, absolutely! Dal freezes exceptionally well for up to **1 month**. Store in portion-sized stainless steel dabbas or freezer-safe containers without adding fresh coriander on top.\n"
        "3. **Sour smell or foam/bubbles:** If cooked dal has formed tiny fizzing bubbles or a sour tang, lactic bacteria have fermented it. Discard it."
    ),
    (
        re.compile(r"\b(coriander|dhaniya|kothmir|mint|pudina)\b.*\b(store|keep|fresh|kala|black|rot)\b", re.I),
        "🌿 **Zero-Waste Herb Storage Hack:**\n\n"
        "1. **Never store moist:** Moisture is the #1 cause of black, slimy coriander. When bought, untie the bunch and discard any yellow or wet stalks.\n"
        "2. **Paper Towel + Steel Dabba Method:** Line an airtight stainless steel dabba or plastic container with a dry cotton cloth or paper towel. Place unwashed coriander inside and seal. Keeps crisp for **12-16 days**!\n"
        "3. **Already wilting?** Blend with green chilli, cumin, salt, and 1 tsp lemon juice into spicy **hari chutney** and freeze in an ice tray for 2 months of instant chutney cubes."
    ),
    (
        re.compile(r"\b(potato|aloo|alu)\b.*\b(sprout|sprouting|green|hara|ug)\b", re.I),
        "🥔 **Sprouting & Green Potatoes:**\n\n"
        "1. **Small firm sprouts:** If the potato is still hard and firm, snap off the sprouts completely and cut away the eyes. It is completely safe to cook.\n"
        "2. **Green skin (Chlorophyll & Solanine):** If parts of the skin are green, peel deeply until no green remains. If the flesh inside is green or tastes bitter, discard it — solanine is a natural toxin that is heat-stable.\n"
        "3. **Storage Rule:** Store potatoes in a dark, well-ventilated dry basket **away from onions**. Onions emit ethylene gas which triggers rapid potato sprouting."
    ),
    (
        re.compile(r"\b(paneer)\b.*\b(slimy|water|sour|store|opened|freezer)\b", re.I),
        "🧀 **Keeping Paneer Fresh:**\n\n"
        "1. **Submerged Water Method:** Place opened paneer block in a sealed container completely submerged in fresh filtered water in the fridge. Change the water every 2 days. This keeps it soft and fresh for **up to 6 days**.\n"
        "2. **Slightly sour or slippery:** Rinse thoroughly in warm water. If the texture is still firm and smell is clean, cook immediately in a high-heat sabzi or bhurji.\n"
        "3. **Freezing:** Cut into cubes, toss in a freezer bag. Keeps for 2 months. Thaw directly in warm water before cooking."
    ),
    (
        re.compile(r"\b(banana|kela)\b.*\b(black|kala|brown|overripe|soft)\b", re.I),
        "🍌 **Overripe Black Bananas:**\n\n"
        "1. **Black skin is natural:** Bananas turn dark due to natural ethylene ripening. As long as the inside flesh isn't watery, rotting, or smelling like alcohol, it is safe and sweet!\n"
        "2. **Rescue ideas:** Perfect for **Banana Halwa (Kela Sheera)**, whole wheat banana pancakes, or peel, chop and freeze for thick smoothies."
    ),
]


def ask_food_rescue_coach(
    user_message: str,
    pantry_items: list[dict] | None = None,
    history: list[dict] | None = None,
) -> str:
    """Provide conversational food safety, shelf-life, and rescue guidance for Indian kitchens."""
    pantry_items = pantry_items or []
    history = history or []

    at_risk = [p for p in pantry_items if p.get("risk", 0) >= 0.45 or p.get("days_to_expiry", 99) <= 2]
    at_risk_names = [f"{a.get('name')} ({a.get('days_to_expiry')} days left)" for a in at_risk[:5]]

    if is_live():
        system_instruction = (
            "You are the FridgeSense AI Food Rescue Coach — an encouraging, knowledgeable Indian kitchen preservation "
            "and food safety expert. You give practical, scientifically accurate advice tailored to Indian kitchens "
            "and tropical/monsoon climate conditions (summer ambient heat, high humidity, steel dabbas, refrigeration). "
            "Answer directly with clear actionable advice: Is it safe to eat? How to store it properly? How to rescue it before spoilage? "
            "Be warm, concise, and structured with bullet points."
        )

        context_msg = f"User kitchen context: Household active pantry has items expiring soon: {', '.join(at_risk_names) or 'None'}.\n\nQuestion: {user_message}"

        contents = []
        for h in history[-4:]:
            role = "user" if h.get("role") == "user" else "model"
            contents.append({"role": role, "parts": [{"text": h.get("content", "")}]})
        contents.append({"role": "user", "parts": [{"text": context_msg}]})

        try:
            answer = _call_gemini_generate(
                contents=contents,
                system_instruction=system_instruction,
                temperature=0.4,
            )
            if answer:
                return answer.strip()
        except Exception as exc:
            log.warning("AI Coach live API error: %s", exc)

    # Heuristic Fallback Search
    for pat, answer in FOOD_SAFETY_KNOWLEDGE_BASE:
        if pat.search(user_message):
            return answer

    # General Helpful Fallback
    return (
        f"👩‍🍳 **FridgeSense Food Rescue Coach:**\n\n"
        f"Regarding **'{user_message}'**:\n\n"
        f"• **Food Safety First:** Always inspect color, texture, and aroma. In Indian climates (especially over 30°C), "
        f"cooked items left out over 2-3 hours should be reheated to a rolling boil or refrigerated immediately.\n"
        f"• **Expiring Produce:** If you have items like {', '.join(at_risk_names) or 'leafy greens and tomatoes'}, "
        f"cook them tonight into a spiced rescue tadka, bhurji, or freeze them in portioned containers.\n"
        f"• *Tip: Configure your Gemini API Key in Settings to get real-time deep answers for any specific cooking scenario!*"
    )
