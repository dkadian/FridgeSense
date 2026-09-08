"""Regenerates the evaluation figures in docs/figures from saved artifacts.

Run after train_spoilage.py:   python3 ml/evaluate.py
"""
from __future__ import annotations

import csv
import json
import os
import sys

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(REPO, "backend"))

from app.ml.gbdt import GradientBoostingClassifier   # noqa: E402
from app.ml.linear import LogisticRegression         # noqa: E402
from app.ml import metrics as M                      # noqa: E402
from generate_dataset import FEATURES                # noqa: E402
from train_spoilage import load, split_by_household, heuristic_scores  # noqa: E402

ART = os.path.join(HERE, "artifacts")
FIG = os.path.join(REPO, "docs", "figures")

INK = "#1d2b26"
ACCENT = "#1f6f4a"
WARN = "#c2610a"
MUTE = "#9aa5a0"


def style(ax, title, xlabel, ylabel):
    ax.set_title(title, fontsize=11, color=INK, pad=10, loc="left", fontweight="bold")
    ax.set_xlabel(xlabel, fontsize=9, color=INK)
    ax.set_ylabel(ylabel, fontsize=9, color=INK)
    ax.tick_params(labelsize=8, colors=INK)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color("#cbd5d0")
    ax.grid(alpha=0.25, linewidth=0.6)


def main():
    os.makedirs(FIG, exist_ok=True)
    X, y, hh, cat = load()
    tr, te = split_by_household(hh)

    gb = GradientBoostingClassifier.from_dict(
        json.load(open(os.path.join(ART, "spoilage_model.json"))))
    lr = LogisticRegression.from_dict(
        json.load(open(os.path.join(ART, "baseline_logistic.json"))))
    card = json.load(open(os.path.join(ART, "model_card.json")))

    p_gb = gb.predict_proba(X[te])
    p_lr = lr.predict_proba(X[te])
    p_hu = heuristic_scores(X[te])
    yt = y[te]

    # ------------------------------------------------------------------ ROC
    fig, ax = plt.subplots(figsize=(5.2, 4.2), dpi=160)
    for p, name, col, ls in ((p_gb, "Gradient boosting", ACCENT, "-"),
                             (p_lr, "Logistic regression", WARN, "--"),
                             (p_hu, "Expiry-date rule", MUTE, ":")):
        fpr, tpr = M.roc_curve(yt, p)
        ax.plot(fpr, tpr, color=col, ls=ls, lw=1.9,
                label="%s  AUC %.3f" % (name, M.roc_auc(yt, p)))
    ax.plot([0, 1], [0, 1], color="#dde3e0", lw=1)
    style(ax, "ROC - will this item be wasted?", "False positive rate", "True positive rate")
    ax.legend(fontsize=8, frameon=False, loc="lower right")
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "roc_curves.png")); plt.close(fig)

    # ------------------------------------------------------------ PR curves
    fig, ax = plt.subplots(figsize=(5.2, 4.2), dpi=160)
    for p, name, col, ls in ((p_gb, "Gradient boosting", ACCENT, "-"),
                             (p_lr, "Logistic regression", WARN, "--"),
                             (p_hu, "Expiry-date rule", MUTE, ":")):
        rc, pr = M.pr_curve(yt, p)
        ax.plot(rc, pr, color=col, ls=ls, lw=1.9,
                label="%s  AP %.3f" % (name, M.average_precision(yt, p)))
    ax.axhline(yt.mean(), color="#dde3e0", lw=1)
    ax.text(0.02, yt.mean() + 0.02, "base rate %.2f" % yt.mean(), fontsize=7, color=MUTE)
    style(ax, "Precision-recall", "Recall", "Precision")
    ax.legend(fontsize=8, frameon=False, loc="upper right")
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "pr_curves.png")); plt.close(fig)

    # ---------------------------------------------------------- calibration
    rows = M.calibration_table(yt, p_gb, n_bins=10)
    fig, ax = plt.subplots(figsize=(5.0, 4.2), dpi=160)
    ax.plot([0, 1], [0, 1], color="#dde3e0", lw=1, label="perfect")
    ax.plot([r["mean_predicted"] for r in rows], [r["observed_rate"] for r in rows],
            "o-", color=ACCENT, lw=1.8, ms=4, label="model")
    style(ax, "Calibration (ECE %.4f)" % M.expected_calibration_error(yt, p_gb),
          "Mean predicted probability", "Observed waste rate")
    ax.legend(fontsize=8, frameon=False)
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "calibration.png")); plt.close(fig)

    # ----------------------------------------------------- feature importance
    imps = card["feature_importances"][:12][::-1]
    fig, ax = plt.subplots(figsize=(6.0, 4.4), dpi=160)
    ax.barh([r["feature"].replace("_", " ") for r in imps],
            [r["importance"] for r in imps], color=ACCENT, height=0.62)
    style(ax, "Which signals drive the risk score", "Share of total split gain", "")
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "feature_importance.png")); plt.close(fig)

    # ------------------------------------------------------------ lift chart
    lift = M.lift_table(yt, p_gb, 10)
    fig, ax = plt.subplots(figsize=(5.6, 4.0), dpi=160)
    ax.bar([r["decile"] for r in lift], [r["waste_rate"] for r in lift],
           color=[ACCENT if r["decile"] <= 2 else "#b9c7c1" for r in lift], width=0.68)
    ax.axhline(yt.mean(), color=WARN, lw=1.2, ls="--")
    ax.text(6.4, yt.mean() + 0.02, "average item  %.2f" % yt.mean(), fontsize=7.5, color=WARN)
    style(ax, "Ranking quality: waste rate by predicted-risk decile",
          "Risk decile (1 = highest predicted risk)", "Actual waste rate")
    ax.set_xticks(range(1, 11))
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "lift_by_decile.png")); plt.close(fig)

    # -------------------------------------------------------- learning curve
    fig, ax = plt.subplots(figsize=(5.6, 4.0), dpi=160)
    ax.plot(gb.train_curve_, color=ACCENT, lw=1.6, label="train")
    if gb.valid_curve_:
        ax.plot(gb.valid_curve_, color=WARN, lw=1.6, label="validation")
        b = int(np.argmin(gb.valid_curve_))
        ax.axvline(b, color=MUTE, ls=":", lw=1.2)
        ax.text(b + 12, max(gb.valid_curve_) * 0.98, "early stop\nround %d" % (b + 1),
                fontsize=7.5, color=MUTE)
    style(ax, "Boosting learning curve", "Boosting round", "Log loss")
    ax.legend(fontsize=8, frameon=False)
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "learning_curve.png")); plt.close(fig)

    # -------------------------------------------------- waste rate by category
    with open(os.path.join(ART, "spoilage_dataset.csv")) as fh:
        drows = list(csv.DictReader(fh))
    agg = {}
    for r in drows:
        agg.setdefault(r["category"], []).append(int(r["wasted"]))
    items = sorted(agg.items(), key=lambda kv: np.mean(kv[1]))
    fig, ax = plt.subplots(figsize=(6.2, 4.8), dpi=160)
    vals = [float(np.mean(v)) for _, v in items]
    ax.barh([k.replace("_", " ") for k, _ in items], vals,
            color=[WARN if v > 0.3 else ACCENT for v in vals], height=0.66)
    style(ax, "Simulated waste incidence by food category",
          "Share of purchased items wasted", "")
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "waste_by_category.png")); plt.close(fig)

    # ------------------------------------------------------- per-category AUC
    pc = sorted(card["per_category_auc"], key=lambda r: r["roc_auc"])
    fig, ax = plt.subplots(figsize=(6.2, 4.8), dpi=160)
    ax.barh([r["category"].replace("_", " ") for r in pc], [r["roc_auc"] for r in pc],
            color=ACCENT, height=0.66)
    ax.set_xlim(0.5, 1.0)
    style(ax, "Model discrimination holds across every category", "ROC AUC", "")
    fig.tight_layout(); fig.savefig(os.path.join(FIG, "per_category_auc.png")); plt.close(fig)

    print("figures written to", FIG)
    for f in sorted(os.listdir(FIG)):
        print("  ", f, os.path.getsize(os.path.join(FIG, f)) // 1024, "KB")


if __name__ == "__main__":
    main()
