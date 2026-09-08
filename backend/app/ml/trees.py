"""Histogram-based regression tree used as the weak learner for boosting.

The tree is grown on first- and second-order gradients of the loss (g and h)
rather than on raw targets, which is what lets a single implementation serve
any twice-differentiable objective. Split quality uses the regularised gain

    gain = 1/2 * [ GL^2/(HL+lam) + GR^2/(HR+lam) - G^2/(H+lam) ] - gamma

and leaf weights use the corresponding Newton step, w = -G / (H + lam).

Features are pre-binned into quantile buckets once, so finding the best split
at a node costs one bincount per feature instead of a sort.
"""
from __future__ import annotations

import numpy as np


class BinMapper:
    """Maps continuous features onto integer quantile bins."""

    def __init__(self, max_bins: int = 64):
        self.max_bins = int(max_bins)
        self.cuts: list[np.ndarray] = []

    def fit(self, X: np.ndarray) -> "BinMapper":
        X = np.asarray(X, dtype=np.float64)
        self.cuts = []
        qs = np.linspace(0.0, 1.0, self.max_bins + 1)[1:-1]
        for j in range(X.shape[1]):
            col = X[:, j]
            cuts = np.unique(np.quantile(col, qs))
            # A constant feature yields no cut points and is simply never split.
            self.cuts.append(cuts.astype(np.float64))
        return self

    def transform(self, X: np.ndarray) -> np.ndarray:
        X = np.asarray(X, dtype=np.float64)
        out = np.empty(X.shape, dtype=np.int32)
        for j, cuts in enumerate(self.cuts):
            # bin b  <=>  cuts[b-1] < x <= cuts[b]
            out[:, j] = np.searchsorted(cuts, X[:, j], side="left")
        return out

    def fit_transform(self, X: np.ndarray) -> np.ndarray:
        return self.fit(X).transform(X)

    @property
    def n_bins(self) -> list[int]:
        return [len(c) + 1 for c in self.cuts]


class RegressionTree:
    """A single tree, stored as flat arrays so it serialises to JSON directly."""

    def __init__(
        self,
        max_depth: int = 3,
        min_samples_leaf: int = 20,
        min_child_weight: float = 1e-3,
        lam: float = 1.0,
        gamma: float = 0.0,
    ):
        self.max_depth = int(max_depth)
        self.min_samples_leaf = int(min_samples_leaf)
        self.min_child_weight = float(min_child_weight)
        self.lam = float(lam)
        self.gamma = float(gamma)
        # node arrays
        self.feature: list[int] = []
        self.threshold: list[float] = []
        self.left: list[int] = []
        self.right: list[int] = []
        self.value: list[float] = []
        self.n_node_samples: list[int] = []
        self.gain_by_feature: np.ndarray | None = None

    # ------------------------------------------------------------------ fit
    def fit(
        self,
        Xb: np.ndarray,
        g: np.ndarray,
        h: np.ndarray,
        cuts: list[np.ndarray],
        n_bins: list[int],
        feature_subset: np.ndarray | None = None,
    ) -> "RegressionTree":
        self.feature, self.threshold, self.left, self.right = [], [], [], []
        self.value, self.n_node_samples = [], []
        n_features = Xb.shape[1]
        self.gain_by_feature = np.zeros(n_features, dtype=np.float64)
        self._cuts = cuts
        self._n_bins = n_bins
        self._features = (
            np.arange(n_features) if feature_subset is None else np.asarray(feature_subset)
        )
        idx = np.arange(Xb.shape[0], dtype=np.int64)
        self._grow(Xb, g, h, idx, depth=0)
        del self._cuts, self._n_bins, self._features
        return self

    def _new_node(self) -> int:
        self.feature.append(-1)
        self.threshold.append(0.0)
        self.left.append(-1)
        self.right.append(-1)
        self.value.append(0.0)
        self.n_node_samples.append(0)
        return len(self.feature) - 1

    def _leaf_value(self, G: float, H: float) -> float:
        return float(-G / (H + self.lam))

    def _grow(self, Xb, g, h, idx, depth) -> int:
        node = self._new_node()
        G = float(g[idx].sum())
        H = float(h[idx].sum())
        self.value[node] = self._leaf_value(G, H)
        self.n_node_samples[node] = int(idx.size)

        if depth >= self.max_depth or idx.size < 2 * self.min_samples_leaf:
            return node

        best = self._best_split(Xb, g, h, idx, G, H)
        if best is None:
            return node
        feat, bin_idx, gain = best

        col = Xb[idx, feat]
        left_mask = col <= bin_idx
        left_idx, right_idx = idx[left_mask], idx[~left_mask]
        if left_idx.size < self.min_samples_leaf or right_idx.size < self.min_samples_leaf:
            return node

        self.feature[node] = int(feat)
        self.threshold[node] = float(self._cuts[feat][bin_idx])
        self.gain_by_feature[feat] += gain
        self.left[node] = self._grow(Xb, g, h, left_idx, depth + 1)
        self.right[node] = self._grow(Xb, g, h, right_idx, depth + 1)
        return node

    def _best_split(self, Xb, g, h, idx, G, H):
        best_gain = self.gamma
        best = None
        gi, hi = g[idx], h[idx]
        parent = G * G / (H + self.lam)
        for feat in self._features:
            nb = self._n_bins[feat]
            if nb < 2:
                continue
            bins = Xb[idx, feat]
            Gh = np.bincount(bins, weights=gi, minlength=nb)
            Hh = np.bincount(bins, weights=hi, minlength=nb)
            GL = np.cumsum(Gh)[:-1]
            HL = np.cumsum(Hh)[:-1]
            GR = G - GL
            HR = H - HL
            with np.errstate(divide="ignore", invalid="ignore"):
                gain = 0.5 * (
                    GL * GL / (HL + self.lam) + GR * GR / (HR + self.lam) - parent
                )
            ok = (HL >= self.min_child_weight) & (HR >= self.min_child_weight)
            gain = np.where(ok, gain, -np.inf)
            if gain.size == 0:
                continue
            b = int(np.argmax(gain))
            if gain[b] > best_gain:
                best_gain = float(gain[b])
                best = (int(feat), b, float(gain[b]))
        return best

    # -------------------------------------------------------------- predict
    def predict(self, X: np.ndarray) -> np.ndarray:
        X = np.asarray(X, dtype=np.float64)
        feature = np.asarray(self.feature)
        threshold = np.asarray(self.threshold, dtype=np.float64)
        left = np.asarray(self.left)
        right = np.asarray(self.right)
        value = np.asarray(self.value, dtype=np.float64)

        node = np.zeros(X.shape[0], dtype=np.int64)
        active = feature[node] >= 0
        while active.any():
            rows = np.nonzero(active)[0]
            f = feature[node[rows]]
            go_left = X[rows, f] <= threshold[node[rows]]
            nxt = np.where(go_left, left[node[rows]], right[node[rows]])
            node[rows] = nxt
            active = np.zeros(X.shape[0], dtype=bool)
            active[rows] = feature[nxt] >= 0
        return value[node]

    # ------------------------------------------------------------ serialise
    def to_dict(self) -> dict:
        return {
            "feature": [int(v) for v in self.feature],
            "threshold": [float(v) for v in self.threshold],
            "left": [int(v) for v in self.left],
            "right": [int(v) for v in self.right],
            "value": [float(v) for v in self.value],
            "n_node_samples": [int(v) for v in self.n_node_samples],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "RegressionTree":
        t = cls()
        t.feature = list(d["feature"])
        t.threshold = list(d["threshold"])
        t.left = list(d["left"])
        t.right = list(d["right"])
        t.value = list(d["value"])
        t.n_node_samples = list(d.get("n_node_samples", []))
        return t

    @property
    def n_leaves(self) -> int:
        return sum(1 for f in self.feature if f < 0)
