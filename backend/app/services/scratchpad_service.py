"""Dedicated parsing service for unstructured Hinglish text, WhatsApp grocery lists,
and quick notes into structured FridgeSense pantry items.

Provides hybrid intelligence:
1. Gemini LLM NLP extraction (when GEMINI_API_KEY is active)
2. High-precision rule-based colloquial parser with Indian kitchen unit conversions
   (aadha kilo -> 500g, ek pav -> 250g, gaddi -> bunch grams, dozen -> eggs/banana count)
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import re

from ..knowledge import Knowledge, get_knowledge
from . import llm_service, pantry_service

log = logging.getLogger(__name__)

# Exhaustive colloquial quantity rules for Indian kitchen language
COLLOQUIAL_RULES: list[tuple[re.Pattern, float, str]] = [
    # Aadha kilo / half kg
    (re.compile(r"\b(aadha|adha|adha\s*kilo|aadha\s*kg|half\s*kg|1/2\s*kg|0\.5\s*kg)\b", re.I), 500.0, "colloquial half kg (500g)"),
    # Ek pav / 1 pao / 250g
    (re.compile(r"\b(ek\s*pav|1\s*pav|ek\s*pao|1\s*pao|pav\s*kilo|pao\s*kilo|1/4\s*kg|0\.25\s*kg)\b", re.I), 250.0, "colloquial ek pav (250g)"),
    # Teen pav / 750g
    (re.compile(r"\b(teen\s*pav|3\s*pav|teen\s*pao|3\s*pao|paun\s*kilo|3/4\s*kg|0\.75\s*kg)\b", re.I), 750.0, "colloquial 3 pav (750g)"),
    # Derh kilo / 1.5 kg
    (re.compile(r"\b(derh\s*kilo|dedh\s*kilo|1\.5\s*kg|1\.5kg|one\s*and\s*half\s*kg)\b", re.I), 1500.0, "colloquial derh kilo (1500g)"),
    # Dhai kilo / 2.5 kg
    (re.compile(r"\b(dhai\s*kilo|2\.5\s*kg|2\.5kg|two\s*and\s*half\s*kg)\b", re.I), 2500.0, "colloquial dhai kilo (2500g)"),
    # Dozen patterns
    (re.compile(r"\b(\d+)\s*(?:dozen|darjan)\b", re.I), -10.0, "dozens"),
    (re.compile(r"\b(ek|1)\s*(?:dozen|darjan)\b", re.I), -11.0, "1 dozen"),
    (re.compile(r"\b(aadha|half)\s*(?:dozen|darjan)\b", re.I), -12.0, "half dozen"),
    # Grams pattern: e.g. 200g, 250 gm, 500 grams
    (re.compile(r"(\d+(?:\.\d+)?)\s*(?:g|gm|gms|gram|grams)\b", re.I), -1.0, "grams read directly"),
    # Kg pattern: e.g. 3kg, 0.5 kg, 2 kilo
    (re.compile(r"(\d+(?:\.\d+)?)\s*(?:kg|kgs|kilo|kilos)\b", re.I), -2.0, "kg read directly"),
    # Litre pattern: e.g. 1L, 2 litre, 500ml
    (re.compile(r"(\d+(?:\.\d+)?)\s*(?:l|ltr|litre|litres)\b", re.I), -3.0, "litre read directly"),
    (re.compile(r"(\d+(?:\.\d+)?)\s*(?:ml)\b", re.I), -4.0, "ml read directly"),
    # Packets / bunches / heads
    (re.compile(r"(\d+)\s*(?:packet|pack|pkt|thaili|dabba|can|bottle|bunch|gaddi|mutthi|head|piece|pc|nag)\b", re.I), -5.0, "units read"),
    (re.compile(r"\b(ek|do|teen|char|chaar|paanch|panch|chheh|che)\s*(?:packet|pack|pkt|thaili|dabba|bunch|gaddi|mutthi)\b", re.I), -6.0, "hindi count units"),
    # Bare count with item: e.g. "2 pyaz", "3 tamatar", "6 eggs"
    (re.compile(r"^(\d+)\s+([a-zA-Z_\s]+)$", re.I), -7.0, "bare count"),
]

HINDI_NUMS = {
    "ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4,
    "paanch": 5, "panch": 5, "chheh": 6, "che": 6,
}

# Extensive dictionary of Indian produce, dairy, staples, and condiments
HINGLISH_VOCAB: dict[str, str] = {
    # Dairy
    "doodh": "milk", "dudh": "milk", "milk": "milk", "amul milk": "milk", "toned milk": "milk",
    "dahi": "curd", "curd": "curd", "yogurt": "curd",
    "paneer": "paneer", "panir": "paneer", "cottage cheese": "paneer",
    "makkhan": "butter", "makhan": "butter", "butter": "butter", "amul butter": "butter",
    "ghee": "ghee", "clarified butter": "ghee",
    "chaas": "buttermilk", "chhaachh": "buttermilk", "lassi": "buttermilk", "buttermilk": "buttermilk",
    "cheese": "cheese", "malai": "cream", "cream": "cream",
    # Produce - Vegetables
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
    "tel": "cooking_oil", "cooking oil": "cooking_oil", "refined oil": "cooking_oil",
    "mustard oil": "mustard_oil", "sarson oil": "mustard_oil",
    "maggi": "noodles", "noodles": "noodles", "pasta": "pasta",
    "sprouts": "sprouts",
    "chai patti": "tea", "tea": "tea", "coffee": "coffee",
    "cheeni": "sugar", "sugar": "sugar", "gur": "jaggery", "jaggery": "jaggery",
    "namak": "salt", "salt": "salt",
}


def _recommended_container(category: str, storage: str, food_id: str) -> str:
    """Recommend the optimal container type to maximize food preservation."""
    cat = (category or "").lower()
    stor = (storage or "").lower()
    fid = (food_id or "").lower()

    if fid in ("paneer", "tofu"):
        return "airtight"
    if cat == "dairy":
        return "steel_dabba"
    if fid in ("spinach", "coriander", "mint", "methi", "curry_leaves", "lettuce"):
        return "airtight"
    if fid in ("onion", "potato", "garlic", "ginger"):
        return "paper_mesh"
    if stor == "fridge":
        return "airtight"
    return "default"


def _parse_single_line(line: str, kn: Knowledge) -> tuple[str | None, float, str, float]:
    """Parse one colloquial item line, extracting catalog food_id, mass in grams,
    source justification, and match confidence (0.0 to 1.0)."""
    cleaned = line.lower().strip()
    # Strip list numbers, bullet characters, leading dashes (e.g. "1. ", "• ", "- ")
    cleaned = re.sub(r"^\s*(?:[\*\-\•]|\d+\s*[\.\)\-])\s*", "", cleaned).strip()
    if not cleaned:
        return None, 0.0, "empty", 0.0

    grams = None
    source = "standard catalog quantity"
    confidence = 0.72

    # 1. Identify food term from vocabulary
    matched_fid = None
    for term in sorted(HINGLISH_VOCAB.keys(), key=lambda t: -len(t)):
        if re.search(r"\b" + re.escape(term) + r"\b", cleaned):
            matched_fid = HINGLISH_VOCAB[term]
            break

    # If no direct vocab match, fall back to TF-IDF fuzzy catalog matcher
    if not matched_fid:
        matches = kn.matcher.match(cleaned, top_k=1)
        if matches and matches[0]["score"] >= 0.25:
            matched_fid = matches[0]["food_id"]
            confidence = min(confidence, float(matches[0]["score"]))

    if not matched_fid:
        return None, 0.0, "unrecognized food item", 0.0

    food = kn.food(matched_fid)
    if not food:
        return None, 0.0, "missing catalog metadata", 0.0

    # 2. Extract quantities and unit multipliers
    for pat, val, desc in COLLOQUIAL_RULES:
        m = pat.search(cleaned)
        if not m:
            continue

        if val > 0:
            grams = val
            source = desc
            confidence = 0.90
            break
        elif val == -1.0:  # Direct grams (e.g. 200g)
            grams = float(m.group(1))
            source = f"{m.group(1)}g read directly"
            confidence = 0.96
            break
        elif val == -2.0:  # Direct kilograms (e.g. 1.5 kg)
            grams = float(m.group(1)) * 1000.0
            source = f"{m.group(1)} kg read directly"
            confidence = 0.96
            break
        elif val == -3.0:  # Litres (e.g. 1L)
            grams = float(m.group(1)) * 1000.0
            source = f"{m.group(1)} L read directly"
            confidence = 0.95
            break
        elif val == -4.0:  # Millilitres (e.g. 500ml)
            grams = float(m.group(1))
            source = f"{m.group(1)} ml read directly"
            confidence = 0.95
            break
        elif val == -5.0:  # Count of packets/bunches/heads (e.g. 2 packet doodh, 1 gaddi palak)
            count = float(m.group(1))
            grams = count * float(food.grams_per_unit)
            source = f"{int(count)} {food.unit} ({int(grams)}g)"
            confidence = 0.90
            break
        elif val == -6.0:  # Hindi words + packets (e.g. do packet doodh)
            word = m.group(1).lower()
            count = float(HINDI_NUMS.get(word, 1))
            grams = count * float(food.grams_per_unit)
            source = f"{word} ({int(count)}) {food.unit} ({int(grams)}g)"
            confidence = 0.90
            break
        elif val == -7.0:  # Bare number before item (e.g. "2 pyaz", "6 eggs")
            count = float(m.group(1))
            if food.unit == "dozen":
                grams = (count / 12.0) * float(food.grams_per_unit)
            else:
                grams = count * float(food.grams_per_unit)
            source = f"{int(count)} count ({int(grams)}g)"
            confidence = 0.85
            break
        elif val == -10.0:  # Dozens (e.g. 2 dozen ande)
            count = float(m.group(1))
            grams = count * float(food.grams_per_unit)
            source = f"{int(count)} dozen ({int(grams)}g)"
            confidence = 0.92
            break
        elif val == -11.0:  # 1 dozen
            grams = float(food.grams_per_unit)
            source = f"1 dozen ({int(grams)}g)"
            confidence = 0.92
            break
        elif val == -12.0:  # Half dozen
            grams = float(food.grams_per_unit) * 0.5
            source = f"half dozen ({int(grams)}g)"
            confidence = 0.92
            break

    # Fallback to standard package unit if no explicit quantity was specified
    if grams is None:
        grams = float(food.grams_per_unit)
        source = f"standard {food.unit} ({int(food.grams_per_unit)}g)"

    return matched_fid, grams, source, confidence


def parse_scratchpad_notes(
    text: str,
    kn: Knowledge | None = None,
    purchase_date: str | None = None,
) -> dict:
    """Parse unstructured Hinglish text, WhatsApp grocery lists, or quick notes
    into verified FridgeSense pantry items."""
    kn = kn or get_knowledge()
    today = dt.date.today()
    bought = today
    if purchase_date:
        try:
            bought = dt.date.fromisoformat(str(purchase_date)[:10])
        except ValueError:
            bought = today

    # Intelligent chunking: splits by newlines, semicolons, and commas (not within decimal numbers)
    raw_chunks = re.split(r"[\n\r;]+|(?<!\d),(?!\d)", text or "")
    lines = []
    for c in raw_chunks:
        # Strip bullets/number prefixes
        s = re.sub(r"^\s*(?:[\*\-\•]|\d+\s*[\.\)\-])\s*", "", c.strip()).strip()
        if s:
            lines.append(s)

    if not lines:
        return {
            "purchase_date": bought.isoformat(),
            "mode": "empty",
            "items": [],
            "unmatched": [],
            "stats": {"lines_read": 0, "matched": 0, "unmatched": 0},
        }

    items = []
    unmatched = []

    # 1. Attempt Live LLM Parsing if API key is active
    llm_items = None
    if llm_service.is_live():
        prompt = (
            f"You are an Indian kitchen grocery assistant. Convert the following unstructured Hinglish/English "
            f"grocery list into structured items. Map each item to the closest FridgeSense catalog ID.\n"
            f"Colloquial conversions to apply:\n"
            f"- 'aadha kilo' -> 500g\n"
            f"- 'ek pav' / 'pao' -> 250g\n"
            f"- 'derh kilo' -> 1500g\n"
            f"- 'dhai kilo' -> 2500g\n"
            f"- 'packet doodh' -> 500g or 1000g\n"
            f"- 'darjan anda' -> 12 eggs (600g)\n"
            f"- 'gaddi dhaniya' -> 100g\n"
            f"- 'gaddi palak' -> 250g\n\n"
            f"Text to parse:\n{text}\n\n"
            f"Return strictly a valid JSON array of objects with schema:\n"
            f'[{{"raw": "original text line", "food_id": "catalog_id", "name": "English name", "grams": number, "confidence": 0.0-1.0}}]'
        )
        try:
            raw_resp = llm_service._call_gemini_generate(
                contents=[{"role": "user", "parts": [{"text": prompt}]}],
                response_mime_type="application/json",
                temperature=0.1,
            )
            if raw_resp:
                parsed_json = json.loads(raw_resp)
                if isinstance(parsed_json, list) and len(parsed_json) > 0:
                    llm_items = parsed_json
        except Exception as exc:
            log.warning("LLM text parsing encountered error, reverting to heuristic: %s", exc)

    # 2. Process extracted items
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
                unmatched.append({"line": idx, "text": entry.get("raw") or str(entry), "reason": "unrecognized catalog id"})
                continue

            grams = float(entry.get("grams") or food.grams_per_unit)
            storage = food.storage_default
            expiry = pantry_service.default_expiry(food, storage, bought)
            confidence = float(entry.get("confidence") or 0.92)
            container = _recommended_container(food.category, storage, food.id)

            items.append({
                "line": idx,
                "raw": entry.get("raw") or food.name,
                "food_id": food.id,
                "name": food.name,
                "category": food.category,
                "grams": round(grams, 1),
                "grams_source": "Gemini LLM NLP extraction",
                "unit": food.unit,
                "storage": storage,
                "container": container,
                "is_covered": True,
                "purchase_date": bought.isoformat(),
                "expiry_date": expiry.isoformat(),
                "shelf_life_days": int(food.shelf_days(storage)),
                "confidence": round(confidence, 3),
                "needs_review": bool(confidence < 0.75),
                "review_reason": "" if confidence >= 0.75 else "low confidence",
                "co2e_kg": round(grams / 1000.0 * food.co2e_kg_per_kg, 3),
                "value_inr": round(grams / 1000.0 * food.price_inr_per_kg, 2),
            })
    else:
        # Fallback to deterministic colloquial parser
        for idx, line in enumerate(lines, start=1):
            fid, grams, source, confidence = _parse_single_line(line, kn)
            if not fid:
                unmatched.append({"line": idx, "text": line, "reason": "no colloquial match"})
                continue
            food = kn.food(fid)
            if not food:
                unmatched.append({"line": idx, "text": line, "reason": "missing food catalog entry"})
                continue

            storage = food.storage_default
            expiry = pantry_service.default_expiry(food, storage, bought)
            container = _recommended_container(food.category, storage, food.id)

            items.append({
                "line": idx,
                "raw": line,
                "food_id": food.id,
                "name": food.name,
                "category": food.category,
                "grams": round(grams, 1),
                "grams_source": source,
                "unit": food.unit,
                "storage": storage,
                "container": container,
                "is_covered": True,
                "purchase_date": bought.isoformat(),
                "expiry_date": expiry.isoformat(),
                "shelf_life_days": int(food.shelf_days(storage)),
                "confidence": round(confidence, 3),
                "needs_review": bool(confidence < 0.75),
                "review_reason": "" if confidence >= 0.75 else "needs review",
                "co2e_kg": round(grams / 1000.0 * food.co2e_kg_per_kg, 3),
                "value_inr": round(grams / 1000.0 * food.price_inr_per_kg, 2),
            })

    return {
        "purchase_date": bought.isoformat(),
        "mode": "gemini_live" if llm_items else "heuristic_colloquial",
        "items": items,
        "unmatched": unmatched,
        "stats": {
            "lines_read": len(lines),
            "matched": len(items),
            "unmatched": len(unmatched),
            "total_grams": round(sum(i["grams"] for i in items), 1),
            "total_value_inr": round(sum(i["value_inr"] for i in items), 2),
            "total_co2e_kg": round(sum(i["co2e_kg"] for i in items), 3),
        },
    }
