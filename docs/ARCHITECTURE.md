# FridgeSense — Architecture Specification

## Overview
FridgeSense follows a clean, decoupled architecture:
1. **Frontend:** Single Page Application built with React 18, Vite, and custom CSS custom properties.
2. **Backend:** FastAPI REST API using Python's standard library `sqlite3` driver.
3. **ML Layer:** Pure NumPy implementations of GBDT, Logistic Regression, TF-IDF vectorizer, and Levenshtein fuzzy matcher.

## Data Flow
- **Request Pipeline:** Client -> FastAPI Router -> Service Layer -> Repository Layer -> SQLite DB.
- **ML Scoring:** On-demand feature construction from pantry items & household history -> GBDT inference -> Reason extraction.
- **Recipe Rescue:** Query TF-IDF vector constructed from at-risk ingredients -> Cosine similarity vs recipe matrix -> Ranking by rescue value.
