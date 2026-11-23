"""
WebPulse - Database initialization and connection management.
Uses raw aiosqlite for async SQLite access.
"""

import os
import aiosqlite
from contextlib import asynccontextmanager

# Database path: configurable via DATABASE_URL env var, default to storage/webpulse.db
# resolved relative to project root d:/COMMERCIAL/WEB_CHECKS
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
def _clean_path(path: str) -> str:
    """Strip sqlite:/// prefix and resolve path."""
    if path.startswith("sqlite:///"):
        path = path[len("sqlite:///"):]
    if not os.path.isabs(path):
        path = os.path.abspath(os.path.join(PROJECT_ROOT, path))
    return path

DATABASE_URL = _clean_path(
    os.environ.get(
        "DATABASE_URL",
        os.path.join(PROJECT_ROOT, "storage", "webpulse.db"),
    )
)

# ---------------------------------------------------------------------------
# Table creation SQL
# ---------------------------------------------------------------------------

_CREATE_SCANS = """
CREATE TABLE IF NOT EXISTS scans (
    id              TEXT PRIMARY KEY,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    status          TEXT NOT NULL DEFAULT 'pending'
                        CHECK (status IN ('pending', 'running', 'completed', 'cancelled', 'failed')),
    total_urls      INTEGER NOT NULL DEFAULT 0,
    completed_urls  INTEGER NOT NULL DEFAULT 0,
    progress_pct    REAL NOT NULL DEFAULT 0.0
);
"""

_CREATE_SCAN_RESULTS = """
CREATE TABLE IF NOT EXISTS scan_results (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id             TEXT NOT NULL REFERENCES scans(id) ON DELETE CASCADE,
    original_url        TEXT NOT NULL,
    final_url           TEXT,
    domain              TEXT,
    status              TEXT NOT NULL DEFAULT 'ONLINE'
                            CHECK (status IN (
                                'ONLINE', 'OFFLINE', 'HTTP_ERROR', 'TIMEOUT',
                                'SSL_ERROR', 'DNS_ERROR', 'BROWSER_ERROR', 'BLOCKED'
                            )),
    http_status_code    INTEGER,
    response_time_ms    REAL,
    server_info         TEXT,
    website_title       TEXT,
    screenshot_path     TEXT,
    error_message       TEXT,
    created_at          TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

_CREATE_DNS_RECORDS = """
CREATE TABLE IF NOT EXISTS dns_records (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_result_id      INTEGER NOT NULL REFERENCES scan_results(id) ON DELETE CASCADE,
    domain              TEXT NOT NULL,
    record_type         TEXT NOT NULL,
    record_value        TEXT,
    ttl                 INTEGER,
    lookup_status       TEXT,
    error_message       TEXT,
    lookup_time_ms      REAL
);
"""

_CREATE_SSL_DETAILS = """
CREATE TABLE IF NOT EXISTS ssl_details (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_result_id          INTEGER NOT NULL REFERENCES scan_results(id) ON DELETE CASCADE,
    domain                  TEXT NOT NULL,
    issuer                  TEXT,
    subject                 TEXT,
    valid_from              TEXT,
    expiry_date             TEXT,
    remaining_days          INTEGER,
    hostname_match          INTEGER,
    https_available         INTEGER,
    verification_status     TEXT,
    error_message           TEXT
);
"""

# Optional indices for common queries
_CREATE_INDICES = """
CREATE INDEX IF NOT EXISTS idx_scan_results_scan_id    ON scan_results(scan_id);
CREATE INDEX IF NOT EXISTS idx_dns_records_result_id   ON dns_records(scan_result_id);
CREATE INDEX IF NOT EXISTS idx_ssl_details_result_id   ON ssl_details(scan_result_id);
CREATE INDEX IF NOT EXISTS idx_scans_created_at        ON scans(created_at);
"""


async def init_db(db_path: str | None = None) -> None:
    """Create all tables and indices if they don't already exist."""
    path = _clean_path(db_path) if db_path else DATABASE_URL

    # Ensure the parent directory exists
    os.makedirs(os.path.dirname(path), exist_ok=True)

    async with aiosqlite.connect(path) as db:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA foreign_keys=ON;")
        await db.execute(_CREATE_SCANS)
        await db.execute(_CREATE_SCAN_RESULTS)
        await db.execute(_CREATE_DNS_RECORDS)
        await db.execute(_CREATE_SSL_DETAILS)
        await db.executescript(_CREATE_INDICES)
        await db.commit()


@asynccontextmanager
async def get_db(db_path: str | None = None):
    """Async context manager that yields an optimized aiosqlite connection.

    Usage::

        async with get_db() as db:
            await db.execute(...)
    """
    path = _clean_path(db_path) if db_path else DATABASE_URL
    db = await aiosqlite.connect(path, timeout=30.0)
    try:
        await db.execute("PRAGMA journal_mode=WAL;")
        await db.execute("PRAGMA synchronous=NORMAL;")
        await db.execute("PRAGMA cache_size=10000;")
        await db.execute("PRAGMA busy_timeout=15000;")
        await db.execute("PRAGMA foreign_keys=ON;")
        db.row_factory = aiosqlite.Row  # allow dict-like access on rows
        yield db
    finally:
        await db.close()
