"""Fuzzy lexicon matching for receipt lines.

Receipt text is short, abbreviated and frequently misspelt ("TOMATO DESI 1KG",
"amul buttr 500g", "PANEER FRSH"). Exact lookup fails on all of these, so we
index the catalog on character 3-grams with TF-IDF weighting and match by cosine
similarity. Character n-grams degrade gracefully under typos and truncation,
which whole-word matching does not.

A difflib ratio is blended in as a secondary signal because it rewards correct
character *order*, which n-grams alone partly discard.
"""
from __future__ import annotations

import difflib
import re

import numpy as np

from .tfidf import TfidfVectorizer, cosine_similarity

_CLEAN = re.compile(r"[^a-z0-9 ]+")
_WS = re.compile(r"\s+")


def normalize(text: str) -> str:
    t = _CLEAN.sub(" ", str(text).lower())
    return _WS.sub(" ", t).strip()


def char_ngrams(text: str, n: int = 3) -> list[str]:
    t = " " + normalize(text) + " "
    if len(t) <= n:
        return [t]
    return [t[i:i + n] for i in range(len(t) - n + 1)]


class FuzzyLexiconMatcher:
    """Maps free text onto catalog food ids."""

    def __init__(self, n: int = 3, alpha: float = 0.75):
        self.n = int(n)
        self.alpha = float(alpha)   # weight on n-gram cosine vs difflib ratio
        self.entries: list[dict] = []          # {"food_id", "surface"}
        self.vec = TfidfVectorizer(sublinear_tf=True)
        self._M: np.ndarray | None = None

    def fit(self, catalog: list[dict]) -> "FuzzyLexiconMatcher":
        self.entries = []
        for row in catalog:
            surfaces = {row["name"], row["id"].replace("_", " ")}
            for kw in str(row.get("keywords", "")).split("|"):
                if kw.strip():
                    surfaces.add(kw.strip())
            for s in surfaces:
                self.entries.append({"food_id": row["id"], "surface": normalize(s)})
        docs = [char_ngrams(e["surface"], self.n) for e in self.entries]
        self._M = self.vec.fit_transform(docs)
        return self

    def match(self, query: str, top_k: int = 3, min_score: float = 0.34) -> list[dict]:
        assert self._M is not None, "matcher is not fitted"
        q = normalize(query)
        if not q:
            return []
        qv = self.vec.transform([char_ngrams(q, self.n)])
        sims = cosine_similarity(qv, self._M)[0]

        # Blend in sequence similarity, then keep the best surface per food id.
        best: dict[str, float] = {}
        for idx in np.argsort(-sims)[:60]:
            e = self.entries[idx]
            ratio = difflib.SequenceMatcher(None, q, e["surface"]).ratio()
            score = self.alpha * float(sims[idx]) + (1.0 - self.alpha) * ratio
            # A surface appearing as a whole word inside the query is a strong cue.
            if e["surface"] and re.search(r"\b%s\b" % re.escape(e["surface"]), q):
                score = min(1.0, score + 0.22)
            if score > best.get(e["food_id"], 0.0):
                best[e["food_id"]] = score

        out = [{"food_id": k, "score": round(v, 4)} for k, v in best.items() if v >= min_score]
        out.sort(key=lambda r: -r["score"])
        return out[:top_k]

    def to_dict(self) -> dict:
        return {
            "model_type": "FuzzyLexiconMatcher",
            "version": 1,
            "n": self.n,
            "alpha": self.alpha,
            "entries": self.entries,
            "vectorizer": self.vec.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FuzzyLexiconMatcher":
        m = cls(n=d.get("n", 3), alpha=d.get("alpha", 0.75))
        m.entries = list(d["entries"])
        m.vec = TfidfVectorizer.from_dict(d["vectorizer"])
        docs = [char_ngrams(e["surface"], m.n) for e in m.entries]
        m._M = m.vec.transform(docs)
        return m


# --------------------------------------------------------------- quantity parsing
_QTY = re.compile(
    r"(?P<num>\d+(?:[.,]\d+)?)\s*"
    r"(?P<unit>kgs?|kilo(?:gram)?s?|gms?|grams?|g\b|ltr?s?|litres?|liters?|l\b|ml\b|"
    r"dozens?|doz\b|dzn?\b|pcs?\b|pieces?|packs?|pkts?\b|packets?|"
    r"nos?\b|units?|boxe?s?\b|tins?\b|bottles?|btls?\b|jars?\b|"
    r"trays?\b|bunch(?:es)?|loa(?:f|ves)|heads?\b|bowls?\b|tubs?\b|bars?\b|eac?h?\b)",
    re.I,
)
_TRAILING_PRICE = re.compile(r"(?:rs\.?|inr|₹)?\s*\d+(?:[.,]\d{1,2})?\s*$", re.I)
_LEADING_CODE = re.compile(r"^\s*(?:\d{4,}|\d+\s*[x*])\s*", re.I)

_UNIT_GRAMS = {
    "kg": 1000.0, "kgs": 1000.0, "kilo": 1000.0, "kilos": 1000.0,
    "kilogram": 1000.0, "kilograms": 1000.0,
    "g": 1.0, "gm": 1.0, "gms": 1.0, "gram": 1.0, "grams": 1.0,
    "l": 1000.0, "ltr": 1000.0, "ltrs": 1000.0, "litre": 1000.0, "litres": 1000.0,
    "liter": 1000.0, "liters": 1000.0, "ml": 1.0,
}


# A "piece" is one individual item; a "pack" is one retail container. The
# distinction matters because "EGGS 12 PC" and "PANEER 2 PKT" both give a count
# but mean completely different masses.
_PIECE_UNITS = {"pc", "pcs", "piece", "pieces", "no", "nos", "unit", "units",
                "ea", "each", "head", "heads"}


def parse_quantity(line: str) -> dict:
    """Extract an explicit quantity from a receipt line.

    Returns {"grams": float|None, "count": float|None, "unit": str|None,
    "kind": "weight"|"piece"|"pack"|None}.
    Weight/volume units convert to grams directly; countable units are returned
    as a count so the caller can multiply by the catalog's grams-per-unit.
    """
    m = _QTY.search(line or "")
    if not m:
        return {"grams": None, "count": None, "unit": None, "kind": None}
    num = float(m.group("num").replace(",", "."))
    unit = m.group("unit").lower().rstrip(".")
    if unit in _UNIT_GRAMS:
        return {"grams": num * _UNIT_GRAMS[unit], "count": None, "unit": unit,
                "kind": "weight"}
    if unit.startswith("doz") or unit in ("dz", "dzn"):
        # Normalised to individual pieces so the caller only handles one notion
        # of "count": twelve eggs, not one dozen-shaped object.
        return {"grams": None, "count": num * 12.0, "unit": "dozen", "kind": "piece"}
    if unit in _PIECE_UNITS:
        return {"grams": None, "count": num, "unit": unit, "kind": "piece"}
    return {"grams": None, "count": num, "unit": unit, "kind": "pack"}


def strip_noise(line: str) -> str:
    """Remove till codes, quantities and trailing prices so only the item name
    is left for the matcher."""
    s = _LEADING_CODE.sub("", str(line or ""))
    s = _TRAILING_PRICE.sub("", s)
    s = _QTY.sub(" ", s)
    s = re.sub(r"\b(?:rs\.?|inr|mrp|qty|hsn|tax|cgst|sgst)\b", " ", s, flags=re.I)
    return normalize(s)
