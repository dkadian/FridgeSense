"""Loads the static domain knowledge and trained artifacts exactly once.

Holds the food catalog, the recipe book, the impact factors, the spoilage model,
the recipe retrieval index and the receipt lexicon. Everything is read-only after
load, so a single shared instance is safe across request threads.
"""
from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass, field

import numpy as np

from .config import ARTIFACT_DIR, DATA_DIR
from .ml.gbdt import GradientBoostingClassifier
from .ml.matcher import FuzzyLexiconMatcher
from .ml.tfidf import TfidfVectorizer

# Category ids are snake_case, and mechanically un-snaking them gives "meat fish"
# and "nuts oils". Only the ids that read badly need an entry; everything else
# falls through to the mechanical version, which is fine for "vegetables".
CATEGORY_LABELS = {
    "meat_fish": ("meat and fish", "Meat & Fish"),
    "nuts_oils": ("nuts and oils", "Nuts & Oils"),
    "cooked_leftovers": ("leftovers", "Leftovers"),
    "leafy_greens": ("leafy greens", "Leafy Greens"),
}


def category_label(category: str) -> str:
    """Lower case, for use inside a sentence."""
    if category in CATEGORY_LABELS:
        return CATEGORY_LABELS[category][0]
    return (category or "other").replace("_", " ")


def category_title(category: str) -> str:
    """Title case, for headings and chart labels."""
    if category in CATEGORY_LABELS:
        return CATEGORY_LABELS[category][1]
    return (category or "Other").replace("_", " ").title()


STORAGE_CODE = {"pantry": 0, "fridge": 1, "freezer": 2}
STORAGES = ("pantry", "fridge", "freezer")


@dataclass(frozen=True)
class Food:
    id: str
    name: str
    category: str
    perishability: int
    storage_default: str
    shelf: dict = field(default_factory=dict)   # storage -> days (-1 unsuitable)
    co2e_kg_per_kg: float = 0.0
    water_l_per_kg: float = 0.0
    price_inr_per_kg: float = 0.0
    unit: str = "kg"
    grams_per_unit: float = 1000.0
    daily_g_per_person: float = 50.0
    keywords: tuple = ()

    def shelf_days(self, storage: str) -> float:
        v = self.shelf.get(storage, -1)
        return float(v)

    @property
    def best_storage(self) -> str:
        """Longest-keeping storage of the three. Used only by the model feature
        `storage_mismatch`, which was trained against this definition."""
        return max(STORAGES, key=lambda s: self.shelf_days(s))

    @property
    def best_shelf_days(self) -> float:
        return max(self.shelf_days(s) for s in STORAGES)

    @property
    def recommended_storage(self) -> str:
        """Where this food actually belongs, for advice shown to a person.

        This is the curated `storage_default` column, not the longest-keeping
        option, because the two often disagree in ways that matter. A fridge
        keeps onions measurably longer than a pantry does and a freezer keeps
        apples longer still, yet refrigerating onions turns them soft and
        freezing a fresh apple destroys the texture it was bought for. Shelf
        life is only one of the constraints a cook is working under.

        Freezing is therefore never given as ordinary storage advice; it is
        offered separately, and labelled, as a deliberate preservation step.
        """
        default = self.storage_default
        if self.shelf_days(default) > 0:
            return default
        viable = [s for s in STORAGES if self.shelf_days(s) > 0]
        return max(viable, key=lambda s: self.shelf_days(s)) if viable else "fridge"

    @property
    def recommended_shelf_days(self) -> float:
        return self.shelf_days(self.recommended_storage)

    def freezer_gain(self, current_storage: str) -> float:
        """Extra days the freezer buys over where the item is now, 0 if none."""
        if self.shelf_days("freezer") <= 0 or current_storage == "freezer":
            return 0.0
        return max(0.0, self.shelf_days("freezer") - max(1.0, self.shelf_days(current_storage)))

    def allowed_storages(self) -> list[str]:
        return [s for s in STORAGES if self.shelf_days(s) > 0]

    @property
    def ethylene_type(self) -> str:
        """'producer', 'sensitive', or 'neutral'."""
        info = ETHYLENE_DATA.get(self.id)
        return info.get("type", "neutral") if info else "neutral"

    @property
    def ethylene_tip(self) -> str:
        info = ETHYLENE_DATA.get(self.id)
        return info.get("tip", "") if info else ""

    @property
    def ethylene_antagonists(self) -> list[str]:
        info = ETHYLENE_DATA.get(self.id)
        return list(info.get("antagonists", [])) if info else []


ETHYLENE_DATA = {
    # High Ethylene Gas Producers
    "banana": {
        "type": "producer",
        "rate": "high",
        "tip": "Releases high ethylene gas. Keep hung or separated from greens and cucumbers to prevent rapid yellowing.",
    },
    "apple": {
        "type": "producer",
        "rate": "high",
        "tip": "Strong ethylene emitter. Store away from leafy greens, carrots, and potatoes.",
    },
    "tomato": {
        "type": "producer",
        "rate": "high",
        "tip": "Emits ethylene gas as it ripens. Keep away from cucumbers and leafy greens.",
    },
    "onion": {
        "type": "producer",
        "rate": "moderate",
        "tip": "Emits ethylene gas and moisture. Never store in the same basket as potatoes!",
    },
    "mango": {
        "type": "producer",
        "rate": "high",
        "tip": "High ethylene fruit. Keep in a separate fruit bowl or wrap individually.",
    },
    "papaya": {
        "type": "producer",
        "rate": "high",
        "tip": "Releases ethylene rapidly as it softens. Store away from other vegetables.",
    },
    "guava": {
        "type": "producer",
        "rate": "moderate",
        "tip": "Emits ethylene during ripening. Keep in a dedicated fruit section.",
    },
    "spring_onion": {
        "type": "producer",
        "rate": "moderate",
        "tip": "Moderate ethylene emitter. Keep in crisper separated from delicate herbs.",
    },
    # Highly Ethylene Sensitive Produce
    "potato": {
        "type": "sensitive",
        "antagonists": ["onion", "apple", "banana"],
        "tip": "Highly sensitive to onions and apples. Co-storing causes rapid sprouting and rot.",
    },
    "spinach": {
        "type": "sensitive",
        "antagonists": ["apple", "banana", "tomato", "mango"],
        "tip": "Extremely sensitive to ethylene. Keep in a sealed container away from apples, bananas, and tomatoes.",
    },
    "methi": {
        "type": "sensitive",
        "antagonists": ["apple", "banana", "tomato"],
        "tip": "Ethylene turns leaves yellow within 48 hours. Keep in a sealed crisper container.",
    },
    "coriander": {
        "type": "sensitive",
        "antagonists": ["apple", "banana", "tomato"],
        "tip": "Quickly turns yellow and decays near ethylene producers. Store in an airtight container.",
    },
    "mint": {
        "type": "sensitive",
        "antagonists": ["apple", "banana", "tomato"],
        "tip": "Store in an airtight jar or container away from ripening fruit.",
    },
    "curry_leaves": {
        "type": "sensitive",
        "antagonists": ["apple", "banana", "tomato"],
        "tip": "Sensitive to ethylene gas. Keep wrapped in a paper towel in a sealed container.",
    },
    "lettuce": {
        "type": "sensitive",
        "antagonists": ["apple", "banana", "tomato"],
        "tip": "Develops russet spotting and browning near apples and bananas.",
    },
    "amaranth": {
        "type": "sensitive",
        "antagonists": ["apple", "banana", "tomato"],
        "tip": "Ethylene gas accelerates leaf yellowing and slimy breakdown.",
    },
    "cucumber": {
        "type": "sensitive",
        "antagonists": ["apple", "banana", "tomato"],
        "tip": "Turns yellow and mushy if kept next to tomatoes, apples, or bananas.",
    },
    "broccoli": {
        "type": "sensitive",
        "antagonists": ["apple", "banana", "tomato"],
        "tip": "Ethylene yellows the florets prematurely.",
    },
    "cauliflower": {
        "type": "sensitive",
        "antagonists": ["apple", "banana", "tomato"],
        "tip": "Sensitive to ethylene gas; causes browning and dark spotting of florets.",
    },
    "carrot": {
        "type": "sensitive",
        "antagonists": ["apple", "banana"],
        "tip": "Develops bitterness and softens if exposed to high ethylene.",
    },
    "okra": {
        "type": "sensitive",
        "antagonists": ["apple", "banana", "tomato"],
        "tip": "Ethylene accelerates browning and slimy decay.",
    },
    "watermelon": {
        "type": "sensitive",
        "antagonists": ["apple", "banana"],
        "tip": "Ethylene softens flesh and causes rind decay.",
    },
}



class Knowledge:
    def __init__(self, data_dir: str = DATA_DIR, artifact_dir: str = ARTIFACT_DIR):
        self.data_dir = data_dir
        self.artifact_dir = artifact_dir
        self.foods: dict[str, Food] = {}
        self.recipes: list[dict] = []
        self.recipe_by_id: dict[str, dict] = {}
        self.factors: dict = {}
        self.model: GradientBoostingClassifier | None = None
        self.model_card: dict = {}
        self.recipe_vec: TfidfVectorizer | None = None
        self.recipe_matrix: np.ndarray | None = None
        self.matcher: FuzzyLexiconMatcher | None = None
        self.warnings: list[str] = []
        self._load()

    # ------------------------------------------------------------------ load
    def _load(self) -> None:
        self._load_catalog()
        self._load_recipes()
        self._load_factors()
        self._load_model()
        self._load_indexes()

    def _load_catalog(self) -> None:
        path = os.path.join(self.data_dir, "food_catalog.csv")
        with open(path) as fh:
            for r in csv.DictReader(fh):
                self.foods[r["id"]] = Food(
                    id=r["id"],
                    name=r["name"],
                    category=r["category"],
                    perishability=int(float(r["perishability"])),
                    storage_default=r["storage_default"],
                    shelf={
                        "pantry": float(r["shelf_pantry"]),
                        "fridge": float(r["shelf_fridge"]),
                        "freezer": float(r["shelf_freezer"]),
                    },
                    co2e_kg_per_kg=float(r["co2e_kg_per_kg"]),
                    water_l_per_kg=float(r["water_l_per_kg"]),
                    price_inr_per_kg=float(r["price_inr_per_kg"]),
                    unit=r["unit"],
                    grams_per_unit=float(r["grams_per_unit"]),
                    daily_g_per_person=float(r["daily_g_per_person"]),
                    keywords=tuple(k for k in r["keywords"].split("|") if k),
                )

    def _load_recipes(self) -> None:
        path = os.path.join(self.data_dir, "recipes.json")
        with open(path) as f:
            self.recipes = json.load(f)
        self.recipe_by_id = {r["id"]: r for r in self.recipes}

    def _load_factors(self) -> None:
        path = os.path.join(self.data_dir, "impact_factors.json")
        with open(path) as f:
            self.factors = json.load(f)

    def _load_model(self) -> None:
        path = os.path.join(self.artifact_dir, "spoilage_model.json")
        if not os.path.exists(path):
            self.warnings.append(
                "spoilage_model.json missing - run 'python3 ml/train_spoilage.py'. "
                "Risk scoring will fall back to a shelf-life heuristic."
            )
            return
        with open(path) as f:
            payload = json.load(f)
        self.model = GradientBoostingClassifier.from_dict(payload)
        self.operating_threshold = float(payload.get("operating_threshold", 0.5))
        card = os.path.join(self.artifact_dir, "model_card.json")
        if os.path.exists(card):
            with open(card) as f:
                self.model_card = json.load(f)

    def _load_indexes(self) -> None:
        rpath = os.path.join(self.artifact_dir, "recipe_index.json")
        if os.path.exists(rpath):
            with open(rpath) as f:
                self.recipe_vec = TfidfVectorizer.from_dict(json.load(f)["vectorizer"])
        else:
            self.recipe_vec = TfidfVectorizer(sublinear_tf=True).fit(
                [[i["id"] for i in r["ingredients"]] for r in self.recipes])
            self.warnings.append("recipe_index.json missing - fitted in memory instead.")
        self.recipe_matrix = self.recipe_vec.transform(
            [[i["id"] for i in r["ingredients"]] for r in self.recipes])

        mpath = os.path.join(self.artifact_dir, "lexicon_index.json")
        if os.path.exists(mpath):
            with open(mpath) as f:
                self.matcher = FuzzyLexiconMatcher.from_dict(json.load(f))
        else:
            rows = [
                {"id": f.id, "name": f.name, "keywords": "|".join(f.keywords)}
                for f in self.foods.values()
            ]
            self.matcher = FuzzyLexiconMatcher().fit(rows)
            self.warnings.append("lexicon_index.json missing - fitted in memory instead.")

    # ------------------------------------------------------------- accessors
    def food(self, food_id: str) -> Food | None:
        return self.foods.get(food_id)

    def risk_bands(self) -> list[dict]:
        return self.factors.get("risk_bands", [])

    def band_for(self, score: float) -> dict:
        for b in self.risk_bands():          # ordered high threshold first
            if score >= float(b["min"]):
                return b
        return {"band": "low", "label": "Comfortable", "color": "#1f6f4a", "min": 0.0}

    def equivalence(self, key: str, default: float = 0.0) -> float:
        return float(self.factors.get("equivalences", {}).get(key, default))

    def search_foods(self, query: str, limit: int = 12) -> list[Food]:
        q = (query or "").strip().lower()
        if not q:
            return sorted(self.foods.values(), key=lambda f: f.name)[:limit]
        exact, partial = [], []
        for f in self.foods.values():
            hay = " ".join([f.name.lower(), f.id.replace("_", " ")] + list(f.keywords))
            if hay.startswith(q) or f.name.lower().startswith(q):
                exact.append(f)
            elif q in hay:
                partial.append(f)
        out = sorted(exact, key=lambda f: f.name) + sorted(partial, key=lambda f: f.name)
        if not out and self.matcher:
            for m in self.matcher.match(q, top_k=limit):
                f = self.foods.get(m["food_id"])
                if f:
                    out.append(f)
        return out[:limit]


_KNOWLEDGE: Knowledge | None = None


def get_knowledge() -> Knowledge:
    global _KNOWLEDGE
    if _KNOWLEDGE is None:
        _KNOWLEDGE = Knowledge()
    return _KNOWLEDGE
