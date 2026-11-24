import os
import sys
import asyncio
import logging
from pathlib import Path
from contextlib import asynccontextmanager

if sys.platform == "win32":
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception:
        pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.app.config import settings
from backend.app.database.db import init_db
from backend.app.api.routes import router
from backend.app.screenshots.capture import get_browser_pool

# Ensure storage directories exist at import time
os.makedirs(settings.screenshots_dir, exist_ok=True)
os.makedirs(settings.reports_dir, exist_ok=True)
db_dir = os.path.dirname(settings.db_path)
if db_dir:
    os.makedirs(db_dir, exist_ok=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # --- Startup ---
    # Create storage directories
    os.makedirs(settings.screenshots_dir, exist_ok=True)
    os.makedirs(settings.reports_dir, exist_ok=True)

    # Ensure the directory for the SQLite database exists
    db_dir = os.path.dirname(settings.db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)

    # Initialize the database (create tables)
    await init_db()

    # Pre-warm high-speed persistent browser workers in background
    try:
        get_browser_pool().start()
    except Exception as pool_init_err:
        logging.getLogger(__name__).warning("Browser pool pre-warm note: %s", pool_init_err)

    yield
    # --- Shutdown ---
    try:
        get_browser_pool().shutdown()
    except Exception:
        pass


app = FastAPI(
    title="WebPulse API",
    description="Website health & DNS audit platform – backend API",
    version="1.0.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Direct Screenshot File Handler
# ---------------------------------------------------------------------------
@app.get("/screenshots/{filename:path}")
async def get_screenshot(filename: str):
    name = os.path.basename(filename)
    filepath = os.path.join(settings.screenshots_dir, name)
    if os.path.isfile(filepath):
        return FileResponse(filepath, media_type="image/png")
    raise HTTPException(status_code=404, detail="Screenshot not found.")


# ---------------------------------------------------------------------------
# Static file mounts
# ---------------------------------------------------------------------------
app.mount(
    "/screenshots",
    StaticFiles(directory=settings.screenshots_dir),
    name="screenshots",
)
app.mount(
    "/reports",
    StaticFiles(directory=settings.reports_dir),
    name="reports",
)

# ---------------------------------------------------------------------------
# API router & Direct Database Reset Handlers
# ---------------------------------------------------------------------------
app.include_router(router)


@app.api_route("/api/database/reset", methods=["GET", "POST", "DELETE"])
@app.api_route("/database/reset", methods=["GET", "POST", "DELETE"])
@app.api_route("/api/reset-db", methods=["GET", "POST", "DELETE"])
async def root_reset_database():
    from backend.app.api.routes import reset_database
    return await reset_database()


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------
@app.get("/api/health", tags=["health"])
async def health_check():
    return {"status": "healthy", "service": "WebPulse API"}


# ---------------------------------------------------------------------------
# Production Single-Port Frontend Mount (Colab, Docker, Standalone)
# ---------------------------------------------------------------------------
frontend_dist = settings.project_root / "frontend" / "dist"
if frontend_dist.is_dir():
    @app.exception_handler(404)
    async def spa_404_handler(request: Request, exc: HTTPException):
        index_file = frontend_dist / "index.html"
        if not request.url.path.startswith(("/api", "/screenshots", "/reports", "/ws")) and index_file.is_file():
            return FileResponse(str(index_file))
        return JSONResponse({"detail": "Not Found"}, status_code=404)

    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")

