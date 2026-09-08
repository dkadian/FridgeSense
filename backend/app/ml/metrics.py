"""Classification metrics implemented on NumPy.

Everything the project needs to report an honest model card: threshold metrics,
ranking metrics, probability calibration and a lift table.
"""
from __future__ import annotations

import numpy as np


def confusion(y, p, threshold: float = 0.5) -> dict:
    y = np.asarray(y).ravel().astype(int)
    yhat = (np.asarray(p).ravel() >= threshold).astype(int)
    tp = int(np.sum((y == 1) & (yhat == 1)))
    tn = int(np.sum((y == 0) & (yhat == 0)))
    fp = int(np.sum((y == 0) & (yhat == 1)))
    fn = int(np.sum((y == 1) & (yhat == 0)))
    return {"tp": tp, "tn": tn, "fp": fp, "fn": fn}


def _safe(a: float, b: float) -> float:
    return float(a / b) if b else 0.0


def classification_report(y, p, threshold: float = 0.5) -> dict:
    c = confusion(y, p, threshold)
    tp, tn, fp, fn = c["tp"], c["tn"], c["fp"], c["fn"]
    precision = _safe(tp, tp + fp)
    recall = _safe(tp, tp + fn)
    specificity = _safe(tn, tn + fp)
    f1 = _safe(2 * precision * recall, precision + recall)
    return {
        "threshold": float(threshold),
        "accuracy": _safe(tp + tn, tp + tn + fp + fn),
        "precision": precision,
        "recall": recall,
        "specificity": specificity,
        "f1": f1,
        "balanced_accuracy": (recall + specificity) / 2.0,
        "confusion": c,
    }


def roc_curve(y, p):
    y = np.asarray(y).ravel().astype(int)
    p = np.asarray(p).ravel()
    order = np.argsort(-p)
    y = y[order]
    P = int(y.sum())
    N = int(y.size - P)
    tps = np.cumsum(y)
    fps = np.cumsum(1 - y)
    tpr = np.concatenate([[0.0], tps / P if P else tps * 0.0])
    fpr = np.concatenate([[0.0], fps / N if N else fps * 0.0])
    return fpr, tpr


def roc_auc(y, p) -> float:
    """Rank-based AUC with correct handling of tied scores."""
    y = np.asarray(y).ravel().astype(int)
    p = np.asarray(p).ravel()
    P, N = int(y.sum()), int((1 - y).sum())
    if P == 0 or N == 0:
        return float("nan")
    order = np.argsort(p, kind="mergesort")
    ps = p[order]
    ranks = np.empty(p.size, dtype=np.float64)
    i = 0
    while i < ps.size:
        j = i
        while j + 1 < ps.size and ps[j + 1] == ps[i]:
            j += 1
        ranks[i : j + 1] = 0.5 * (i + j) + 1.0  # average rank for ties
        i = j + 1
    r = np.empty_like(ranks)
    r[order] = ranks
    return float((r[y == 1].sum() - P * (P + 1) / 2.0) / (P * N))


def pr_curve(y, p):
    y = np.asarray(y).ravel().astype(int)
    p = np.asarray(p).ravel()
    order = np.argsort(-p)
    y = y[order]
    tps = np.cumsum(y)
    fps = np.cumsum(1 - y)
    P = int(y.sum())
    precision = tps / np.maximum(tps + fps, 1)
    recall = tps / P if P else tps * 0.0
    return recall, precision


def average_precision(y, p) -> float:
    recall, precision = pr_curve(y, p)
    if recall.size == 0:
        return float("nan")
    dr = np.diff(np.concatenate([[0.0], recall]))
    return float(np.sum(precision * dr))


def brier_score(y, p) -> float:
    y = np.asarray(y).ravel().astype(float)
    return float(np.mean((np.asarray(p).ravel() - y) ** 2))


def log_loss(y, p, eps: float = 1e-12) -> float:
    y = np.asarray(y).ravel().astype(float)
    q = np.clip(np.asarray(p).ravel(), eps, 1 - eps)
    return float(-np.mean(y * np.log(q) + (1 - y) * np.log(1 - q)))


def calibration_table(y, p, n_bins: int = 10) -> list[dict]:
    y = np.asarray(y).ravel().astype(float)
    p = np.asarray(p).ravel()
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    out = []
    for k in range(n_bins):
        lo, hi = edges[k], edges[k + 1]
        m = (p >= lo) & (p < hi) if k < n_bins - 1 else (p >= lo) & (p <= hi)
        if not m.any():
            continue
        out.append({
            "bin": "%.1f-%.1f" % (lo, hi),
            "n": int(m.sum()),
            "mean_predicted": float(p[m].mean()),
            "observed_rate": float(y[m].mean()),
        })
    return out


def expected_calibration_error(y, p, n_bins: int = 10) -> float:
    rows = calibration_table(y, p, n_bins)
    n = sum(r["n"] for r in rows) or 1
    return float(sum(r["n"] * abs(r["mean_predicted"] - r["observed_rate"]) for r in rows) / n)


def lift_table(y, p, n_groups: int = 10) -> list[dict]:
    """How well the ranking concentrates real waste in the top deciles - this
    is the metric that actually matters for an 'eat me first' list.
    """
    y = np.asarray(y).ravel().astype(float)
    p = np.asarray(p).ravel()
    order = np.argsort(-p)
    y = y[order]
    base = y.mean() if y.size else 0.0
    groups = np.array_split(np.arange(y.size), n_groups)
    out = []
    for i, gi in enumerate(groups):
        if gi.size == 0:
            continue
        rate = float(y[gi].mean())
        out.append({
            "decile": i + 1,
            "n": int(gi.size),
            "waste_rate": rate,
            "lift": float(rate / base) if base else 0.0,
        })
    return out


def best_threshold(y, p, objective: str = "f1") -> dict:
    """Pick an operating point by sweeping candidate thresholds."""
    p = np.asarray(p).ravel()
    cands = np.unique(np.round(np.linspace(0.05, 0.95, 91), 4))
    best, best_score = None, -np.inf
    for t in cands:
        rep = classification_report(y, p, float(t))
        score = rep[objective] if objective in rep else rep["f1"]
        if score > best_score:
            best_score, best = score, rep
    return best


def full_report(y, p, threshold: float = 0.5) -> dict:
    return {
        "n": int(np.asarray(y).size),
        "positive_rate": float(np.asarray(y).ravel().mean()),
        "roc_auc": roc_auc(y, p),
        "average_precision": average_precision(y, p),
        "log_loss": log_loss(y, p),
        "brier_score": brier_score(y, p),
        "expected_calibration_error": expected_calibration_error(y, p),
        "at_threshold": classification_report(y, p, threshold),
        "calibration": calibration_table(y, p),
        "lift": lift_table(y, p),
    }
