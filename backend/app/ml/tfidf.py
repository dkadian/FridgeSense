"""TF-IDF vectoriser and cosine similarity for recipe retrieval.

Documents are recipes represented as their ingredient-id token lists, so the
vocabulary is the catalog itself and no text normalisation is required. Rare
ingredients (paneer, mushroom) therefore carry more weight than ubiquitous ones
(onion, salt), which is exactly the behaviour we want: matching on 'mushroom'
is far more informative than matching on 'onion'.
"""
from __future__ import annotations

import numpy as np


class TfidfVectorizer:
    def __init__(self, sublinear_tf: bool = True, smooth_idf: bool = True):
        self.sublinear_tf = bool(sublinear_tf)
        self.smooth_idf = bool(smooth_idf)
        self.vocabulary_: dict[str, int] = {}
        self.idf_: np.ndarray | None = None

    def fit(self, docs: list[list[str]]) -> "TfidfVectorizer":
        vocab: dict[str, int] = {}
        for d in docs:
            for tok in d:
                if tok not in vocab:
                    vocab[tok] = len(vocab)
        self.vocabulary_ = vocab
        n_docs = len(docs)
        df = np.zeros(len(vocab), dtype=np.float64)
        for d in docs:
            for tok in set(d):
                df[vocab[tok]] += 1.0
        if self.smooth_idf:
            self.idf_ = np.log((1.0 + n_docs) / (1.0 + df)) + 1.0
        else:
            self.idf_ = np.log(n_docs / np.maximum(df, 1.0)) + 1.0
        return self

    def transform(self, docs: list[list[str]], weights: list[dict] | None = None) -> np.ndarray:
        assert self.idf_ is not None, "vectoriser is not fitted"
        M = np.zeros((len(docs), len(self.vocabulary_)), dtype=np.float64)
        for i, d in enumerate(docs):
            w = weights[i] if weights else None
            for tok in d:
                j = self.vocabulary_.get(tok)
                if j is None:
                    continue  # unseen ingredient contributes nothing
                M[i, j] += float(w.get(tok, 1.0)) if w else 1.0
        if self.sublinear_tf:
            M_pos = np.maximum(M, 1.0)
            M = np.where(M > 0, 1.0 + np.log(M_pos), 0.0)
        M *= self.idf_
        norms = np.linalg.norm(M, axis=1, keepdims=True)
        safe_norms = np.where(norms > 1e-12, norms, 1.0)
        return np.where(norms > 1e-12, M / safe_norms, 0.0)

    def fit_transform(self, docs: list[list[str]]) -> np.ndarray:
        return self.fit(docs).transform(docs)

    def to_dict(self) -> dict:
        return {
            "model_type": "TfidfVectorizer",
            "version": 1,
            "sublinear_tf": self.sublinear_tf,
            "smooth_idf": self.smooth_idf,
            "vocabulary": self.vocabulary_,
            "idf": [float(v) for v in (self.idf_ if self.idf_ is not None else [])],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "TfidfVectorizer":
        v = cls(sublinear_tf=d.get("sublinear_tf", True), smooth_idf=d.get("smooth_idf", True))
        v.vocabulary_ = dict(d["vocabulary"])
        v.idf_ = np.asarray(d["idf"], dtype=np.float64)
        return v


def cosine_similarity(A: np.ndarray, B: np.ndarray) -> np.ndarray:
    """Rows of A against rows of B. Inputs are assumed L2-normalised already,
    but we normalise defensively so the function is safe on raw counts too.
    """
    A = np.atleast_2d(np.asarray(A, dtype=np.float64))
    B = np.atleast_2d(np.asarray(B, dtype=np.float64))
    nA = np.linalg.norm(A, axis=1, keepdims=True)
    safe_nA = np.where(nA > 1e-12, nA, 1.0)
    A = np.where(nA > 1e-12, A / safe_nA, 0.0)

    nB = np.linalg.norm(B, axis=1, keepdims=True)
    safe_nB = np.where(nB > 1e-12, nB, 1.0)
    B = np.where(nB > 1e-12, B / safe_nB, 0.0)
    with np.errstate(all="ignore"):
        return A @ B.T



