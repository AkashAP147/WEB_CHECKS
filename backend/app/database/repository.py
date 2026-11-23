"""
WebPulse - Database repository layer.
Every function takes an aiosqlite connection (``db``) as its first argument and
uses parameterised queries exclusively.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

import aiosqlite


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _row_to_dict(row: aiosqlite.Row | None) -> dict | None:
    """Convert an aiosqlite.Row (sqlite3.Row) to a plain dict."""
    if row is None:
        return None
    return dict(row)


def _rows_to_dicts(rows: list[aiosqlite.Row]) -> list[dict]:
    return [dict(r) for r in rows]


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Scans
# ---------------------------------------------------------------------------

async def create_scan(db: aiosqlite.Connection, scan_id: str, total_urls: int) -> dict:
    """Insert a new scan row and return it as a dict."""
    now = _utcnow_iso()
    await db.execute(
        """
        INSERT INTO scans (id, created_at, status, total_urls, completed_urls, progress_pct)
        VALUES (?, ?, 'pending', ?, 0, 0.0)
        """,
        (scan_id, now, total_urls),
    )
    await db.commit()
    return {
        "id": scan_id,
        "created_at": now,
        "status": "pending",
        "total_urls": total_urls,
        "completed_urls": 0,
        "progress_pct": 0.0,
    }


async def update_scan_status(
    db: aiosqlite.Connection,
    scan_id: str,
    status: str,
    completed_urls: int | None = None,
) -> None:
    """Update a scan's status and optionally its completed_urls / progress_pct."""
    if completed_urls is not None:
        # Recalculate progress
        row = await db.execute_fetchall(
            "SELECT total_urls FROM scans WHERE id = ?", (scan_id,)
        )
        total = row[0][0] if row else 1
        progress_pct = round((completed_urls / total) * 100, 2) if total else 0.0
        await db.execute(
            """
            UPDATE scans
               SET status = ?, completed_urls = ?, progress_pct = ?
             WHERE id = ?
            """,
            (status, completed_urls, progress_pct, scan_id),
        )
    else:
        await db.execute(
            "UPDATE scans SET status = ? WHERE id = ?",
            (status, scan_id),
        )
    await db.commit()


async def get_scan(db: aiosqlite.Connection, scan_id: str) -> dict | None:
    """Return a single scan row as dict, or None."""
    cursor = await db.execute("SELECT * FROM scans WHERE id = ?", (scan_id,))
    row = await cursor.fetchone()
    return _row_to_dict(row)


# ---------------------------------------------------------------------------
# Scan results
# ---------------------------------------------------------------------------

async def save_scan_result(
    db: aiosqlite.Connection, scan_id: str, result_data: dict, commit: bool = True
) -> int:
    """Insert a scan_result row and return its auto-generated id."""
    valid_statuses = {
        'ONLINE', 'OFFLINE', 'HTTP_ERROR', 'TIMEOUT',
        'SSL_ERROR', 'DNS_ERROR', 'BROWSER_ERROR', 'BLOCKED'
    }
    raw_status = str(result_data.get("status") or "ONLINE").upper()
    if raw_status not in valid_statuses:
        raw_status = "BLOCKED" if "BLOCK" in raw_status else "OFFLINE"

    cursor = await db.execute(
        """
        INSERT INTO scan_results
            (scan_id, original_url, final_url, domain, status,
             http_status_code, response_time_ms, server_info,
             website_title, screenshot_path, error_message, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            scan_id,
            result_data.get("original_url"),
            result_data.get("final_url"),
            result_data.get("domain"),
            raw_status,
            result_data.get("http_status_code"),
            result_data.get("response_time_ms"),
            result_data.get("server_info"),
            result_data.get("website_title"),
            result_data.get("screenshot_path"),
            result_data.get("error_message"),
            _utcnow_iso(),
        ),
    )
    if commit:
        await db.commit()
    return cursor.lastrowid  # type: ignore[return-value]


async def get_scan_results(db: aiosqlite.Connection, scan_id: str) -> list[dict]:
    """Return all scan_result rows for a given scan."""
    cursor = await db.execute(
        "SELECT * FROM scan_results WHERE scan_id = ? ORDER BY id", (scan_id,)
    )
    rows = await cursor.fetchall()
    return _rows_to_dicts(rows)


async def get_recent_cached_result(
    db: aiosqlite.Connection, url_or_domain: str
) -> tuple[dict, list[dict], dict | None] | None:
    """Check if URL or domain was already scanned within the last 24 hours.
    Returns (result_dict, dns_records, ssl_details) if cached, else None."""
    cursor = await db.execute(
        """
        SELECT id, original_url, final_url, domain, status,
               http_status_code, response_time_ms, server_info,
               website_title, screenshot_path, error_message, created_at
        FROM scan_results
        WHERE (original_url = ? OR domain = ? OR final_url = ?)
          AND created_at >= datetime('now', '-24 hours')
        ORDER BY id DESC
        LIMIT 1
        """,
        (url_or_domain, url_or_domain, url_or_domain),
    )
    row = await cursor.fetchone()
    if not row:
        return None
    res = _row_to_dict(row)
    cached_id = res["id"]

    # Fetch DNS records
    dns_cursor = await db.execute(
        """
        SELECT domain, record_type, record_value, ttl, lookup_status, error_message, lookup_time_ms
        FROM dns_records WHERE scan_result_id = ?
        """,
        (cached_id,),
    )
    dns_rows = await dns_cursor.fetchall()
    dns_recs = _rows_to_dicts(dns_rows)

    # Fetch SSL details
    ssl_cursor = await db.execute(
        "SELECT * FROM ssl_details WHERE scan_result_id = ? LIMIT 1",
        (cached_id,),
    )
    ssl_row = await ssl_cursor.fetchone()
    ssl_data = _row_to_dict(ssl_row)

    return res, dns_recs, ssl_data


# ---------------------------------------------------------------------------
# DNS records
# ---------------------------------------------------------------------------

async def save_dns_records(
    db: aiosqlite.Connection,
    scan_result_id: int,
    records_list: list[dict],
    commit: bool = True,
) -> None:
    """Bulk-insert DNS record rows for a given scan result."""
    if not records_list:
        return
    await db.executemany(
        """
        INSERT INTO dns_records
            (scan_result_id, domain, record_type, record_value,
             ttl, lookup_status, error_message, lookup_time_ms)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                scan_result_id,
                r.get("domain", ""),
                r.get("record_type", ""),
                r.get("record_value"),
                r.get("ttl"),
                r.get("lookup_status"),
                r.get("error_message"),
                r.get("lookup_time_ms"),
            )
            for r in records_list
        ],
    )
    if commit:
        await db.commit()


async def get_dns_records(
    db: aiosqlite.Connection, scan_result_id: int
) -> list[dict]:
    """Return all DNS records for a given scan result."""
    cursor = await db.execute(
        "SELECT * FROM dns_records WHERE scan_result_id = ? ORDER BY id",
        (scan_result_id,),
    )
    rows = await cursor.fetchall()
    return _rows_to_dicts(rows)


# ---------------------------------------------------------------------------
# SSL details
# ---------------------------------------------------------------------------

async def save_ssl_details(
    db: aiosqlite.Connection,
    scan_result_id: int,
    ssl_data: dict,
    commit: bool = True,
) -> int:
    """Insert an SSL details row and return its id."""
    cursor = await db.execute(
        """
        INSERT INTO ssl_details
            (scan_result_id, domain, issuer, subject, valid_from,
             expiry_date, remaining_days, hostname_match,
             https_available, verification_status, error_message)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            scan_result_id,
            ssl_data.get("domain", ""),
            ssl_data.get("issuer"),
            ssl_data.get("subject"),
            ssl_data.get("valid_from"),
            ssl_data.get("expiry_date"),
            ssl_data.get("remaining_days"),
            int(ssl_data["hostname_match"]) if ssl_data.get("hostname_match") is not None else None,
            int(ssl_data["https_available"]) if ssl_data.get("https_available") is not None else None,
            ssl_data.get("verification_status"),
            ssl_data.get("error_message"),
        ),
    )
    if commit:
        await db.commit()
    return cursor.lastrowid  # type: ignore[return-value]


async def get_ssl_details(
    db: aiosqlite.Connection, scan_result_id: int
) -> dict | None:
    """Return the SSL details row for a scan result, or None."""
    cursor = await db.execute(
        "SELECT * FROM ssl_details WHERE scan_result_id = ? LIMIT 1",
        (scan_result_id,),
    )
    row = await cursor.fetchone()
    if row is None:
        return None
    result = _row_to_dict(row)
    # Convert SQLite integer booleans back to Python bools
    if result and result.get("hostname_match") is not None:
        result["hostname_match"] = bool(result["hostname_match"])
    if result and result.get("https_available") is not None:
        result["https_available"] = bool(result["https_available"])
    return result


# ---------------------------------------------------------------------------
# Scan history
# ---------------------------------------------------------------------------

async def get_scan_history(
    db: aiosqlite.Connection,
    limit: int = 20,
    offset: int = 0,
    search: str | None = None,
    status_filter: str | None = None,
) -> list[dict]:
    """Return paginated scan-history rows with aggregated result counts.

    ``search`` filters by any original_url containing the term.
    ``status_filter`` filters by scan status.
    """
    query = """
        SELECT
            s.id            AS scan_id,
            s.created_at,
            s.total_urls,
            s.status,
            COALESCE(SUM(CASE WHEN sr.status = 'ONLINE' THEN 1 ELSE 0 END), 0)       AS online_count,
            COALESCE(SUM(CASE WHEN sr.status = 'OFFLINE' THEN 1 ELSE 0 END), 0)       AS offline_count,
            COALESCE(SUM(CASE WHEN sr.status = 'DNS_ERROR' THEN 1 ELSE 0 END), 0)     AS dns_errors,
            COALESCE(SUM(CASE WHEN ssl.verification_status IS NOT NULL
                              AND ssl.verification_status != 'valid' THEN 1 ELSE 0 END), 0) AS ssl_issues
        FROM scans s
        LEFT JOIN scan_results sr ON sr.scan_id = s.id
        LEFT JOIN ssl_details  ssl ON ssl.scan_result_id = sr.id
    """
    params: list[Any] = []
    clauses: list[str] = []

    if search:
        clauses.append("sr.original_url LIKE ?")
        params.append(f"%{search}%")

    if status_filter:
        clauses.append("s.status = ?")
        params.append(status_filter)

    if clauses:
        query += " WHERE " + " AND ".join(clauses)

    query += """
        GROUP BY s.id
        ORDER BY s.created_at DESC
        LIMIT ? OFFSET ?
    """
    params.extend([limit, offset])

    cursor = await db.execute(query, params)
    rows = await cursor.fetchall()
    return _rows_to_dicts(rows)


# ---------------------------------------------------------------------------
# Dashboard stats
# ---------------------------------------------------------------------------

async def get_dashboard_stats(db: aiosqlite.Connection) -> dict:
    """Compute aggregate dashboard statistics across all scans."""
    cursor = await db.execute(
        """
        SELECT
            COUNT(*)                                                           AS total_scanned,
            COALESCE(SUM(CASE WHEN status = 'ONLINE' THEN 1 ELSE 0 END), 0)   AS online_count,
            COALESCE(SUM(CASE WHEN status = 'OFFLINE' THEN 1 ELSE 0 END), 0)  AS offline_count,
            COALESCE(SUM(CASE WHEN status = 'DNS_ERROR' THEN 1 ELSE 0 END), 0) AS dns_errors,
            COALESCE(AVG(response_time_ms), 0)                                 AS avg_response_time
        FROM scan_results
        """
    )
    agg = await cursor.fetchone()
    agg_dict = _row_to_dict(agg) or {
        "total_scanned": 0,
        "online_count": 0,
        "offline_count": 0,
        "dns_errors": 0,
        "avg_response_time": None,
    }

    # SSL issues count
    cursor2 = await db.execute(
        """
        SELECT COUNT(*) AS ssl_issues
        FROM ssl_details
        WHERE verification_status IS NOT NULL
          AND verification_status != 'valid'
        """
    )
    ssl_row = await cursor2.fetchone()
    agg_dict["ssl_issues"] = dict(ssl_row)["ssl_issues"] if ssl_row else 0

    # Recent scans (last 10)
    recent = await get_scan_history(db, limit=10, offset=0)
    agg_dict["recent_scans"] = recent

    return agg_dict


# ---------------------------------------------------------------------------
# Query results across all websites by time range
# ---------------------------------------------------------------------------

async def get_results_by_time_range(
    db: aiosqlite.Connection,
    start_date: str | None = None,
    end_date: str | None = None,
    status_filter: str | None = None,
    limit: int = 500,
) -> list[dict]:
    """Retrieve scan results across all websites filtered by timestamp range."""
    query = """
        SELECT sr.*, s.created_at AS scan_created_at
        FROM scan_results sr
        LEFT JOIN scans s ON s.id = sr.scan_id
    """
    clauses: list[str] = []
    params: list[Any] = []

    if start_date:
        clauses.append("sr.created_at >= ?")
        params.append(start_date)

    if end_date:
        clauses.append("sr.created_at <= ?")
        params.append(end_date)

    if status_filter and status_filter.upper() != "ALL":
        clauses.append("sr.status = ?")
        params.append(status_filter.upper())

    if clauses:
        query += " WHERE " + " AND ".join(clauses)

    query += " ORDER BY sr.created_at DESC LIMIT ?"
    params.append(limit)

    cursor = await db.execute(query, params)
    rows = await cursor.fetchall()
    return _rows_to_dicts(rows)
