"""Runtime configuration, all overridable by environment variable."""
from __future__ import annotations

import os

HERE = os.path.dirname(os.path.abspath(__file__))          # backend/app
BACKEND_DIR = os.path.abspath(os.path.join(HERE, ".."))     # backend
REPO_DIR = os.path.abspath(os.path.join(BACKEND_DIR, ".."))  # repo root

DATA_DIR = os.environ.get("FRIDGESENSE_DATA_DIR", os.path.join(REPO_DIR, "data"))
ARTIFACT_DIR = os.environ.get("FRIDGESENSE_ARTIFACT_DIR",
                              os.path.join(REPO_DIR, "ml", "artifacts"))
DB_PATH = os.environ.get("FRIDGESENSE_DB", os.path.join(BACKEND_DIR, "fridgesense.db"))

# Change this in any real deployment. Kept as a literal default so the project
# runs immediately after clone, which matters for a reviewer.
SECRET_KEY = os.environ.get("FRIDGESENSE_SECRET", "dev-secret-change-me")
TOKEN_TTL_HOURS = int(os.environ.get("FRIDGESENSE_TOKEN_TTL_HOURS", "72"))

CORS_ORIGINS = os.environ.get(
    "FRIDGESENSE_CORS",
    "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173",
).split(",")

# Global prior used to smooth a new user's personal waste rates and to build the
# counterfactual baseline. Source: UNEP Food Waste Index Report 2024.
GLOBAL_WASTE_PRIOR = float(os.environ.get("FRIDGESENSE_WASTE_PRIOR", "0.22"))

# Try loading .env if present
try:
    from dotenv import load_dotenv
    env_file = os.path.join(REPO_DIR, ".env")
    if os.path.exists(env_file):
        load_dotenv(env_file)
    else:
        load_dotenv(os.path.join(BACKEND_DIR, ".env"))
except ImportError:
    pass

# Google Gemini LLM settings
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")

