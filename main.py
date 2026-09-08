"""Root entry point to run the FridgeSense backend application.

Usage:
    python main.py
"""
import os
import sys

# Add backend directory to sys.path
backend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend")
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

import uvicorn

if __name__ == "__main__":
    # Ensure current working directory is backend/ so SQLite DB path resolves relative to backend
    os.chdir(backend_dir)

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    reload = os.environ.get("RELOAD", "true").lower() in ("true", "1", "yes")

    print(f"🚀 Starting FridgeSense Backend on http://{host}:{port}...")
    uvicorn.run("app.main:app", host=host, port=port, reload=reload)
