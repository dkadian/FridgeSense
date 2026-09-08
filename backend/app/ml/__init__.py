"""FridgeSense machine-learning library.

Implemented from scratch on NumPy so that the whole project runs with no heavy
ML dependency: the trained model ships as a plain JSON file that the API loads
at start-up.

Modules
-------
trees      histogram-based regression tree with XGBoost-style split gain
gbdt       gradient boosting classifier on the logistic loss
metrics    classification metrics, ROC/PR curves, calibration
tfidf      TF-IDF vectoriser and cosine similarity for recipe retrieval
serialize  JSON round-trip for every trained artifact
"""

__all__ = ["trees", "gbdt", "metrics", "tfidf", "serialize"]
