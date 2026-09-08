"""L2-regularised logistic regression, used as the interpretable baseline the
boosted model must beat. Full-batch gradient descent with standardisation.
"""
from __future__ import annotations

import numpy as np

from .gbdt import sigmoid, log_loss


class LogisticRegression:
    def __init__(self, lr: float = 0.5, n_iter: int = 4000, l2: float = 1e-3,
                 tol: float = 1e-8, verbose: int = 0):
        self.lr = float(lr)
        self.n_iter = int(n_iter)
        self.l2 = float(l2)
        self.tol = float(tol)
        self.verbose = int(verbose)
        self.w_: np.ndarray | None = None
        self.b_: float = 0.0
        self.mu_: np.ndarray | None = None
        self.sd_: np.ndarray | None = None
        self.feature_names_: list[str] = []
        self.loss_curve_: list[float] = []

    def _scale(self, X):
        return (X - self.mu_) / self.sd_

    def fit(self, X, y, feature_names: list[str] | None = None):
        X = np.asarray(X, dtype=np.float64)
        y = np.asarray(y, dtype=np.float64).ravel()
        self.feature_names_ = list(feature_names) if feature_names else [
            "f%d" % i for i in range(X.shape[1])]
        self.mu_ = X.mean(axis=0)
        self.sd_ = np.where(X.std(axis=0) < 1e-12, 1.0, X.std(axis=0))
        Z = self._scale(X)
        n, d = Z.shape
        self.w_ = np.zeros(d)
        base = float(np.clip(y.mean(), 1e-6, 1 - 1e-6))
        self.b_ = float(np.log(base / (1 - base)))
        prev = np.inf
        self.loss_curve_ = []
        for it in range(self.n_iter):
            p = sigmoid(Z @ self.w_ + self.b_)
            gw = Z.T @ (p - y) / n + self.l2 * self.w_
            gb = float(np.mean(p - y))
            self.w_ -= self.lr * gw
            self.b_ -= self.lr * gb
            if it % 25 == 0:
                loss = log_loss(y, p) + 0.5 * self.l2 * float(self.w_ @ self.w_)
                self.loss_curve_.append(loss)
                if abs(prev - loss) < self.tol:
                    break
                prev = loss
        return self

    def predict_proba(self, X):
        X = np.asarray(X, dtype=np.float64)
        return sigmoid(self._scale(X) @ self.w_ + self.b_)

    def coefficients(self) -> list[dict]:
        order = np.argsort(-np.abs(self.w_))
        return [{"feature": self.feature_names_[i],
                 "coefficient": float(self.w_[i]),
                 "odds_ratio_per_sd": float(np.exp(self.w_[i]))} for i in order]

    def to_dict(self) -> dict:
        return {
            "model_type": "LogisticRegression",
            "version": 1,
            "weights": [float(v) for v in self.w_],
            "bias": float(self.b_),
            "mu": [float(v) for v in self.mu_],
            "sd": [float(v) for v in self.sd_],
            "feature_names": list(self.feature_names_),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "LogisticRegression":
        m = cls()
        m.w_ = np.asarray(d["weights"], dtype=np.float64)
        m.b_ = float(d["bias"])
        m.mu_ = np.asarray(d["mu"], dtype=np.float64)
        m.sd_ = np.asarray(d["sd"], dtype=np.float64)
        m.feature_names_ = list(d["feature_names"])
        return m
