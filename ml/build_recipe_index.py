"""Fits and saves the retrieval artifacts.

    ml/artifacts/recipe_index.json    TF-IDF over recipe ingredient sets
    ml/artifacts/lexicon_index.json   char-3gram index for receipt matching

Run:  python3 ml/build_recipe_index.py
"""
from __future__ import annotations

import csv
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(REPO, "backend"))

from app.ml.tfidf import TfidfVectorizer, cosine_similarity   # noqa: E402
from app.ml.matcher import FuzzyLexiconMatcher                # noqa: E402
from app.ml.serialize import save_json                        # noqa: E402

DATA = os.path.join(REPO, "data")
ART = os.path.join(HERE, "artifacts")


def main():
    catalog = list(csv.DictReader(open(os.path.join(DATA, "food_catalog.csv"))))
    recipes = json.load(open(os.path.join(DATA, "recipes.json")))

    docs = [[i["id"] for i in r["ingredients"]] for r in recipes]
    vec = TfidfVectorizer(sublinear_tf=True)
    M = vec.fit_transform(docs)

    save_json({
        "model_type": "RecipeIndex",
        "version": 1,
        "recipe_ids": [r["id"] for r in recipes],
        "vectorizer": vec.to_dict(),
    }, os.path.join(ART, "recipe_index.json"), indent=1)

    matcher = FuzzyLexiconMatcher().fit(catalog)
    save_json(matcher.to_dict(), os.path.join(ART, "lexicon_index.json"))

    # ---- quick retrieval sanity check, printed so the run is self-verifying
    print("recipe index: %d recipes, %d ingredient vocabulary" % (len(recipes), len(vec.vocabulary_)))
    print("lexicon index: %d surface forms over %d foods"
          % (len(matcher.entries), len({e["food_id"] for e in matcher.entries})))

    probes = [
        ["spinach", "paneer", "onion"],
        ["cooked_rice", "curd"],
        ["bread", "eggs", "milk"],
        ["okra", "onion", "tomato"],
        ["coriander", "mint"],
    ]
    print("\nretrieval spot-check")
    by_id = {r["id"]: r for r in recipes}
    for p in probes:
        sims = cosine_similarity(vec.transform([p]), M)[0]
        top = np.argsort(-sims)[:3]
        names = ", ".join("%s (%.2f)" % (by_id[recipes[t]["id"]]["title"], sims[t]) for t in top)
        print("  %-34s -> %s" % ("+".join(p), names))

    # Verify the saved artifacts reload to identical results.
    v2 = TfidfVectorizer.from_dict(json.load(open(os.path.join(ART, "recipe_index.json")))["vectorizer"])
    m2 = FuzzyLexiconMatcher.from_dict(json.load(open(os.path.join(ART, "lexicon_index.json"))))
    ok_v = np.allclose(vec.transform(probes), v2.transform(probes))
    ok_m = matcher.match("amul buttr 500g") == m2.match("amul buttr 500g")
    print("\nreload check: vectorizer %s, matcher %s" % ("OK" if ok_v else "FAIL",
                                                         "OK" if ok_m else "FAIL"))
    if not (ok_v and ok_m):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
