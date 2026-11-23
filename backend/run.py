import uvicorn
import sys
import os
import asyncio

if sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception:
        pass

backend_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(backend_dir)
sys.path.insert(0, project_root)

from backend.app.main import app  # noqa: E402, F401

if __name__ == "__main__":
    reload_enabled = os.getenv("RELOAD", "false").lower() in ("true", "1", "yes")
    uvicorn.run(
        "backend.app.main:app",
        host="0.0.0.0",
        port=8000,
        loop="none" if sys.platform == "win32" else "auto",
        reload=reload_enabled,
        reload_dirs=[backend_dir] if reload_enabled else None,
        reload_excludes=["*.db", "*.db-wal", "*.db-shm", "*.png", "*.pdf", "*.xlsx", "storage/*"] if reload_enabled else None,
    )
