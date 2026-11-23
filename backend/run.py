import uvicorn
import sys
import os

backend_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(backend_dir)
sys.path.insert(0, project_root)

from backend.app.main import app  # noqa: E402, F401

if __name__ == "__main__":
    uvicorn.run(
        "backend.app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=[backend_dir],
        reload_excludes=["*.db", "*.db-wal", "*.db-shm", "*.png", "*.pdf", "*.xlsx", "storage/*"],
    )
