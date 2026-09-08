"""Gradient boosting classifier on the logistic loss.

Additive model  F(x) = F0 + lr * sum_m tree_m(x),  p = sigmoid(F(x)).

At each round the gradient and Hessian of the binomial deviance are

    g = p - y        h = p * (1 - p)

and a regression tree is grown on (g, h) using the Newton-step leaf weights in
trees.RegressionTree. Row subsampling and feature subsampling are supported for
variance reduction, and an optional validation split drives early stopping on
log loss.
"""
from __future__ import annotations

import numpy as np

from .trees import BinMapper, RegressionTree


def sigmoid(z: np.ndarray) -> np.ndarray:
    # Branch on sign to avoid overflow in exp for large-magnitude scores.
    z = np.asarray(z, dtype=np.float64)
    out = np.empty_like(z)
    pos = z >= 0
    out[pos] = 1.0 / (1.0 + np.exp(-z[pos]))
    ez = np.exp(z[~pos])
    out[~pos] = ez / (1.0 + ez)
    return out


def log_loss(y: np.ndarray, p: np.ndarray, eps: float = 1e-12) -> float:
    p = np.clip(p, eps, 1.0 - eps)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


class GradientBoostingClassifier:
    def __init__(
        self,
        n_estimators: int = 300,
        learning_rate: float = 0.06,
        max_depth: int = 4,
        min_samples_leaf: int = 20,
        min_child_weight: float = 1.0,
        lam: float = 1.0,
        gamma: float = 0.0,
        subsample: float = 0.8,
        colsample: float = 1.0,
        max_bins: int = 64,
        early_stopping_rounds: int | None = 30,
        validation_fraction: float = 0.15,
        random_state: int = 42,
        verbose: int = 0,
    ):
        self.n_estimators = int(n_estimators)
        self.learning_rate = float(learning_rate)
        self.max_depth = int(max_depth)
        self.min_samples_leaf = int(min_samples_leaf)
        self.min_child_weight = float(min_child_weight)
        self.lam = float(lam)
        self.gamma = float(gamma)
        self.subsample = float(subsample)
        self.colsample = float(colsample)
        self.max_bins = int(max_bins)
        self.early_stopping_rounds = early_stopping_rounds
        self.validation_fraction = float(validation_fraction)
        self.random_state = int(random_state)
        self.verbose = int(verbose)

        self.trees: list[RegressionTree] = []
        self.base_score_ = 0.0
        self.feature_names_: list[str] = []
        self.feature_importances_: np.ndarray | None = None
        self.train_curve_: list[float] = []
        self.valid_curve_: list[float] = []
        self.best_iteration_: int = 0

    # ------------------------------------------------------------------ fit
    def fit(self, X, y, feature_names: list[str] | None = None):
        X = np.asarray(X, dtype=np.float64)
        y = np.asarray(y, dtype=np.float64).ravel()
        n, n_feat = X.shape
        self.feature_names_ = list(feature_names) if feature_names else [
            "f%d" % i for i in range(n_feat)
        ]
        rng = np.random.default_rng(self.random_state)

        use_val = bool(self.early_stopping_rounds) and self.validation_fraction > 0
        if use_val:
            perm = rng.permutation(n)
            n_val = max(1, int(round(self.validation_fraction * n)))
            val_i, tr_i = perm[:n_val], perm[n_val:]
        else:
            tr_i = np.arange(n)
            val_i = np.array([], dtype=np.int64)

        Xtr, ytr = X[tr_i], y[tr_i]
        Xva, yva = X[val_i], y[val_i]

        self.bin_mapper_ = BinMapper(self.max_bins).fit(Xtr)
        Xtr_b = self.bin_mapper_.transform(Xtr)
        cuts, n_bins = self.bin_mapper_.cuts, self.bin_mapper_.n_bins

        base_rate = float(np.clip(ytr.mean(), 1e-6, 1 - 1e-6))
        self.base_score_ = float(np.log(base_rate / (1 - base_rate)))

        F_tr = np.full(ytr.shape[0], self.base_score_)
        F_va = np.full(yva.shape[0], self.base_score_) if use_val else None

        importances = np.zeros(n_feat)
        best_val, best_iter, since_best = np.inf, 0, 0
        self.trees, self.train_curve_, self.valid_curve_ = [], [], []

        n_sub = max(1, int(round(self.subsample * ytr.shape[0])))
        n_col = max(1, int(round(self.colsample * n_feat)))

        for m in range(self.n_estimators):
            p = sigmoid(F_tr)
            g = p - ytr
            h = np.maximum(p * (1 - p), 1e-6)

            if self.subsample < 1.0:
                rows = rng.choice(ytr.shape[0], size=n_sub, replace=False)
            else:
                rows = np.arange(ytr.shape[0])
            feats = (
                rng.choice(n_feat, size=n_col, replace=False)
                if self.colsample < 1.0
                else None
            )

            tree = RegressionTree(
                max_depth=self.max_depth,
                min_samples_leaf=self.min_samples_leaf,
                min_child_weight=self.min_child_weight,
                lam=self.lam,
                gamma=self.gamma,
            )
            # Gradients outside the subsample are zeroed so the tree only sees
            # the sampled rows while keeping array shapes aligned.
            gm = np.zeros_like(g)
            hm = np.zeros_like(h)
            gm[rows] = g[rows]
            hm[rows] = h[rows]
            tree.fit(Xtr_b, gm, hm, cuts, n_bins, feature_subset=feats)

            if tree.gain_by_feature is not None:
                importances += tree.gain_by_feature

            F_tr += self.learning_rate * tree.predict(Xtr)
            self.trees.append(tree)
            self.train_curve_.append(log_loss(ytr, sigmoid(F_tr)))

            if use_val:
                F_va += self.learning_rate * tree.predict(Xva)
                vl = log_loss(yva, sigmoid(F_va))
                self.valid_curve_.append(vl)
                if vl < best_val - 1e-6:
                    best_val, best_iter, since_best = vl, m + 1, 0
                else:
                    since_best += 1
                    if since_best >= int(self.early_stopping_rounds):
                        if self.verbose:
                            print("early stop at round %d (best %d, val logloss %.4f)"
                                  % (m + 1, best_iter, best_val))
                        break
            if self.verbose and (m + 1) % max(1, self.verbose) == 0:
                msg = "round %4d  train %.4f" % (m + 1, self.train_curve_[-1])
                if use_val:
                    msg += "  valid %.4f" % self.valid_curve_[-1]
                print(msg)

        self.best_iteration_ = best_iter if use_val and best_iter > 0 else len(self.trees)
        # Discard trees grown after the best validation round.
        self.trees = self.trees[: self.best_iteration_]
        total = importances.sum()
        self.feature_importances_ = importances / total if total > 0 else importances
        return self

    # -------------------------------------------------------------- predict
    def decision_function(self, X) -> np.ndarray:
        X = np.asarray(X, dtype=np.float64)
        F = np.full(X.shape[0], self.base_score_)
        for t in self.trees:
            F += self.learning_rate * t.predict(X)
        return F

    def predict_proba(self, X) -> np.ndarray:
        return sigmoid(self.decision_function(X))

    def predict(self, X, threshold: float = 0.5) -> np.ndarray:
        return (self.predict_proba(X) >= threshold).astype(int)

    # --------------------------------------------------------- explanations
    def explain(self, x: np.ndarray, top_k: int = 3) -> list[dict]:
        """Per-prediction attribution: the contribution of each feature along
        the decision paths actually taken, summed over trees. Cheap and exact
        for this model class, and enough to tell a user *why* an item is risky.
        """
        x = np.asarray(x, dtype=np.float64).ravel()
        contrib = np.zeros(len(self.feature_names_))
        for t in self.trees:
            node = 0
            while t.feature[node] >= 0:
                f = t.feature[node]
                parent_val = t.value[node]
                nxt = t.left[node] if x[f] <= t.threshold[node] else t.right[node]
                contrib[f] += self.learning_rate * (t.value[nxt] - parent_val)
                node = nxt
        order = np.argsort(-np.abs(contrib))[:top_k]
        return [
            {
                "feature": self.feature_names_[i],
                "contribution": float(contrib[i]),
                "direction": "increases risk" if contrib[i] > 0 else "reduces risk",
            }
            for i in order
            if abs(contrib[i]) > 1e-9
        ]

    # ------------------------------------------------------------ serialise
    def to_dict(self) -> dict:
        return {
            "model_type": "GradientBoostingClassifier",
            "version": 1,
            "base_score": float(self.base_score_),
            "learning_rate": float(self.learning_rate),
            "feature_names": list(self.feature_names_),
            "hyperparameters": {
                "n_estimators": self.n_estimators,
                "learning_rate": self.learning_rate,
                "max_depth": self.max_depth,
                "min_samples_leaf": self.min_samples_leaf,
                "min_child_weight": self.min_child_weight,
                "lam": self.lam,
                "gamma": self.gamma,
                "subsample": self.subsample,
                "colsample": self.colsample,
                "max_bins": self.max_bins,
            },
            "best_iteration": int(self.best_iteration_),
            "n_trees": len(self.trees),
            "feature_importances": (
                [float(v) for v in self.feature_importances_]
                if self.feature_importances_ is not None
                else []
            ),
            "train_curve": [float(v) for v in self.train_curve_],
            "valid_curve": [float(v) for v in self.valid_curve_],
            "trees": [t.to_dict() for t in self.trees],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "GradientBoostingClassifier":
        hp = d.get("hyperparameters", {})
        m = cls(**{k: v for k, v in hp.items() if k in cls.__init__.__code__.co_varnames})
        m.base_score_ = float(d["base_score"])
        m.learning_rate = float(d["learning_rate"])
        m.feature_names_ = list(d["feature_names"])
        m.trees = [RegressionTree.from_dict(t) for t in d["trees"]]
        fi = d.get("feature_importances") or []
        m.feature_importances_ = np.asarray(fi, dtype=np.float64) if fi else None
        m.train_curve_ = list(d.get("train_curve", []))
        m.valid_curve_ = list(d.get("valid_curve", []))
        m.best_iteration_ = int(d.get("best_iteration", len(m.trees)))
        return m
