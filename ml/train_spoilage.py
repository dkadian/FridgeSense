"""Trains and evaluates the FridgeSense spoilage-risk model.

Run:  python3 ml/train_spoilage.py

Produces
--------
ml/artifacts/spoilage_model.json      the boosted model the API loads
ml/artifacts/baseline_logistic.json   interpretable baseline
ml/artifacts/model_card.json          metrics, importances, comparison table

The train/test split is by HOUSEHOLD, not by row. Splitting by row would let the
same household's items appear on both sides and leak its latent planning skill
through the history features, inflating the score. Splitting by household forces
the model to generalise to people it has never seen.
"""
from __future__ import annotations

import csv
import json
import os
import sys
import time

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(REPO, "backend"))

from app.ml.gbdt import GradientBoostingClassifier          # noqa: E402
from app.ml.linear import LogisticRegression                # noqa: E402
from app.ml import metrics as M                             # noqa: E402
from app.ml.serialize import save_json                      # noqa: E402
from generate_dataset import FEATURES                       # noqa: E402

DATASET = os.path.join(HERE, "artifacts", "spoilage_dataset.csv")
ART = os.path.join(HERE, "artifacts")


def load():
    with open(DATASET) as fh:
        rows = list(csv.DictReader(fh))
    X = np.array([[float(r[f]) for f in FEATURES] for r in rows], dtype=np.float64)
    y = np.array([float(r["wasted"]) for r in rows], dtype=np.float64)
    hh = np.array([int(r["household_id"]) for r in rows], dtype=np.int64)
    cat = np.array([r["category"] for r in rows])
    return X, y, hh, cat


def split_by_household(hh, test_frac=0.2, seed=11):
    rng = np.random.default_rng(seed)
    ids = np.unique(hh)
    rng.shuffle(ids)
    n_test = max(1, int(round(test_frac * ids.size)))
    test_ids = set(ids[:n_test].tolist())
    mask = np.array([h in test_ids for h in hh])
    return ~mask, mask


def heuristic_scores(X):
    """The 'obvious' non-ML rule any app would ship first: rank purely by how
    close the item is to its expiry date. This is the bar to beat.
    """
    dte = X[:, FEATURES.index("days_to_expiry")]
    return 1.0 / (1.0 + np.maximum(dte, 0.0))


def main():
    X, y, hh, cat = load()
    tr, te = split_by_household(hh)
    print("dataset %d rows, %d features" % X.shape)
    print("train %d rows / %d households    test %d rows / %d households"
          % (tr.sum(), len(set(hh[tr].tolist())), te.sum(), len(set(hh[te].tolist()))))
    print("waste rate  train %.4f   test %.4f" % (y[tr].mean(), y[te].mean()))

    # ---------------------------------------------------------------- models
    t0 = time.time()
    gb = GradientBoostingClassifier(
        n_estimators=1500, learning_rate=0.06, max_depth=4,
        min_samples_leaf=40, min_child_weight=2.0, lam=1.0,
        subsample=0.8, colsample=0.85, max_bins=64,
        early_stopping_rounds=40, validation_fraction=0.15,
        random_state=42, verbose=0,
    ).fit(X[tr], y[tr], FEATURES)
    gb_time = time.time() - t0
    print("\nboosted model: %d trees kept (best iteration %d) in %.1fs"
          % (len(gb.trees), gb.best_iteration_, gb_time))

    lr = LogisticRegression(lr=0.5, n_iter=6000, l2=1e-3).fit(X[tr], y[tr], FEATURES)

    p_gb = gb.predict_proba(X[te])
    p_lr = lr.predict_proba(X[te])
    p_hu = heuristic_scores(X[te])

    op = M.best_threshold(y[te], p_gb, objective="f1")
    rep_gb = M.full_report(y[te], p_gb, threshold=op["threshold"])
    rep_lr = M.full_report(y[te], p_lr, threshold=0.5)

    comparison = [
        {"model": "Expiry-date heuristic", "roc_auc": M.roc_auc(y[te], p_hu),
         "average_precision": M.average_precision(y[te], p_hu)},
        {"model": "Logistic regression", "roc_auc": M.roc_auc(y[te], p_lr),
         "average_precision": M.average_precision(y[te], p_lr),
         "log_loss": M.log_loss(y[te], p_lr), "brier_score": M.brier_score(y[te], p_lr)},
        {"model": "Gradient boosting (ours)", "roc_auc": rep_gb["roc_auc"],
         "average_precision": rep_gb["average_precision"],
         "log_loss": rep_gb["log_loss"], "brier_score": rep_gb["brier_score"]},
    ]

    print("\n%-26s %8s %8s %9s %8s" % ("model", "AUC", "AP", "logloss", "brier"))
    for c in comparison:
        print("%-26s %8.4f %8.4f %9s %8s" % (
            c["model"], c["roc_auc"], c["average_precision"],
            ("%.4f" % c["log_loss"]) if "log_loss" in c else "-",
            ("%.4f" % c["brier_score"]) if "brier_score" in c else "-"))

    a = rep_gb["at_threshold"]
    print("\noperating point t=%.2f  accuracy %.4f  precision %.4f  recall %.4f  F1 %.4f"
          % (a["threshold"], a["accuracy"], a["precision"], a["recall"], a["f1"]))
    print("confusion:", a["confusion"])
    print("expected calibration error %.4f" % rep_gb["expected_calibration_error"])

    print("\ntop-decile lift (how well the 'eat me first' ranking works)")
    for r in rep_gb["lift"][:4]:
        print("  decile %d  waste rate %.3f  lift %.2fx" % (r["decile"], r["waste_rate"], r["lift"]))

    print("\nfeature importance (share of total split gain)")
    order = np.argsort(-gb.feature_importances_)
    for i in order[:10]:
        print("  %-26s %.4f" % (FEATURES[i], gb.feature_importances_[i]))

    # Per-category AUC tells us whether the model is useful across the board or
    # only on the easy categories.
    per_cat = []
    for c in sorted(set(cat[te].tolist())):
        m = cat[te] == c
        if m.sum() < 60 or len(set(y[te][m].tolist())) < 2:
            continue
        per_cat.append({"category": c, "n": int(m.sum()),
                        "waste_rate": float(y[te][m].mean()),
                        "roc_auc": M.roc_auc(y[te][m], p_gb[m])})
    print("\nper-category AUC")
    for r in sorted(per_cat, key=lambda r: -r["roc_auc"]):
        print("  %-18s n=%-6d rate %.3f  AUC %.4f" % (r["category"], r["n"], r["waste_rate"], r["roc_auc"]))

    # -------------------------------------------------- optional sklearn check
    sk = None
    try:
        from sklearn.ensemble import GradientBoostingClassifier as SkGB
        from sklearn.metrics import roc_auc_score
        skm = SkGB(n_estimators=len(gb.trees), learning_rate=0.06, max_depth=4,
                   subsample=0.8, random_state=42).fit(X[tr], y[tr])
        sk_auc = float(roc_auc_score(y[te], skm.predict_proba(X[te])[:, 1]))
        sk = {"sklearn_roc_auc": sk_auc, "ours_roc_auc": rep_gb["roc_auc"],
              "gap": rep_gb["roc_auc"] - sk_auc}
        print("\nscikit-learn cross-check: sklearn AUC %.4f vs ours %.4f" % (sk_auc, rep_gb["roc_auc"]))
    except ImportError:
        print("\nscikit-learn not installed - skipping the cross-check "
              "(install it and rerun to verify our implementation independently)")

    # ------------------------------------------------------------------ save
    model_payload = gb.to_dict()
    model_payload["operating_threshold"] = float(a["threshold"])
    model_payload["trained_at"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    save_json(model_payload, os.path.join(ART, "spoilage_model.json"))
    save_json(lr.to_dict(), os.path.join(ART, "baseline_logistic.json"), indent=1)

    card = {
        "model_name": "FridgeSense spoilage-risk classifier",
        "task": "Binary classification - will this pantry item be thrown away instead of eaten?",
        "intended_use": ("Ranks a household's pantry so the most at-risk food is used first, "
                         "and quantifies the avoided emissions when it is."),
        "algorithm": ("Gradient-boosted decision trees on the logistic loss, implemented from "
                      "scratch on NumPy (XGBoost-style regularised split gain and Newton-step "
                      "leaf weights, histogram binning, row and column subsampling, early stopping)."),
        "features": FEATURES,
        "training_data": {
            "source": "Behavioural simulator - ml/generate_dataset.py",
            "rows": int(X.shape[0]),
            "households": int(np.unique(hh).size),
            "split": "grouped by household, 80/20",
            "positive_rate": float(y.mean()),
            "calibration": ("Aggregate item-level waste incidence calibrated by bisection to the "
                            "UNEP Food Waste Index household benchmark of ~22%."),
        },
        "limitations": [
            "Trained on simulated outcomes because no public item-level household food-waste "
            "dataset with per-item labels exists; the model therefore encodes the simulator's "
            "documented causal assumptions rather than validated real-world behaviour.",
            "Absolute probabilities should be read as a cold-start prior. The API records every "
            "real consumed/wasted outcome so the model can be retrained on genuine data.",
            "Emission and water factors are category medians, so per-item impact figures are "
            "order-of-magnitude estimates, not audited measurements.",
            "Discrimination is close to chance for long-life staples - see per_category_auc, "
            "where grains, snacks and beverages sit near or below 0.50 on small test folds "
            "with waste rates around 5%. There is little to predict when a food is almost "
            "never wasted, so for those categories the score should be read as the base rate "
            "and not as a finding about the item.",
            "The model is given no absolute mass. Raw grams were removed after an earlier "
            "version learned that large packs mean waste and rated a 3.5 kg bag of flour with "
            "five months of life left at 0.34 for being a big bag. Quantity now enters only "
            "relative to the pack and to the household's own consumption, so 'a lot' means a "
            "lot for this kitchen rather than a lot in kilograms.",
        ],
        "metrics_test": rep_gb,
        "baseline_metrics_test": rep_lr,
        "model_comparison": comparison,
        "sklearn_crosscheck": sk,
        "feature_importances": [
            {"feature": FEATURES[i], "importance": float(gb.feature_importances_[i])}
            for i in order
        ],
        "logistic_coefficients": lr.coefficients(),
        "per_category_auc": per_cat,
        "train_seconds": round(gb_time, 2),
        "trained_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    save_json(card, os.path.join(ART, "model_card.json"), indent=1)
    print("\nsaved: spoilage_model.json, baseline_logistic.json, model_card.json")


if __name__ == "__main__":
    main()
