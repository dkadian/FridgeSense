"""Main entry point to run the FridgeSense backend application.

Usage:
    python main.py
    python backend/main.py
"""
import os
import sys
import uvicorn

# Ensure the backend directory is in sys.path
backend_dir = os.path.dirname(os.path.abspath(__file__))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.main import app

if __name__ == "__main__":
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    reload = os.environ.get("RELOAD", "true").lower() in ("true", "1", "yes")
    
    print(f"🚀 Starting FridgeSense Backend on http://{host}:{port}...")
    uvicorn.run("app.main:app", host=host, port=port, reload=reload)
