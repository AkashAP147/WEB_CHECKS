"""
WebPulse – API routes.

All endpoints are prefixed with /api via the router.
"""

from __future__ import annotations

import asyncio
import io
import os
import time
import uuid
from urllib.parse import urlparse
from datetime import datetime, timezone, timedelta
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

from fastapi import (
    APIRouter,
    BackgroundTasks,
    File,
    HTTPException,
    Query,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import FileResponse, JSONResponse

from backend.app.config import settings
from backend.app.database.db import get_db
from backend.app.database.repository import (
    create_scan,
    get_scan,
    get_scan_results,
    update_scan_status,
    save_scan_result,
    save_dns_records,
    save_ssl_details,
    get_scan_history,
    get_dashboard_stats,
    get_results_by_time_range,
)
from backend.app.utils.url_validator import validate_url, is_safe_url, validate_excel_file
from backend.app.scanners.http_scanner import HttpScanner
from backend.app.dns.analyzer import DNSAnalyzer
from backend.app.ssl_mod.checker import SSLChecker
from backend.app.screenshots.capture import ScreenshotCapture

# Optional heavyweight imports – degrade gracefully when unavailable
try:
    from backend.app.services.scan_service import ScanService
except ImportError:
    ScanService = None  # type: ignore[assignment,misc]

try:
    from backend.app.reports.pdf_generator import PDFReportGenerator
except ImportError:
    PDFReportGenerator = None  # type: ignore[assignment,misc]

try:
    from backend.app.reports.excel_generator import ExcelReportGenerator
except ImportError:
    ExcelReportGenerator = None  # type: ignore[assignment,misc]

try:
    import openpyxl
except ImportError:
    openpyxl = None  # type: ignore[assignment]

router = APIRouter(prefix="/api", tags=["api"])

# ---------------------------------------------------------------------------
# In-memory registry of running scan tasks (scan_id -> asyncio.Task)
# ---------------------------------------------------------------------------
_running_tasks: Dict[str, asyncio.Task] = {}


# ---- helpers ---------------------------------------------------------------

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _extract_urls_from_file(file_bytes: bytes, filename: str = "") -> List[str]:
    """Extract URLs from uploaded spreadsheet/CSV files (.xlsx, .xls, .csv)."""
    from backend.app.utils.url_validator import validate_file_urls
    try:
        return validate_file_urls(file_bytes, filename)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to process file: {exc}",
        ) from exc


def _extract_urls_from_excel(file_bytes: bytes, filename: str = "") -> List[str]:
    """Backwards-compatible alias for _extract_urls_from_file."""
    return _extract_urls_from_file(file_bytes, filename)


async def _run_scan(scan_id: str, urls: List[str]) -> None:
    """Background coroutine that executes a full multi-check scan for all URLs in parallel."""
    http_scanner = HttpScanner()
    dns_analyzer = DNSAnalyzer()
    ssl_checker = SSLChecker()
    screenshot_capturer = ScreenshotCapture(settings.screenshots_dir)

    completed = 0
    total = len(urls)
    progress_lock = asyncio.Lock()

    async with get_db() as db:
        await update_scan_status(db, scan_id, "running", completed_urls=0)

    # Dual concurrency control:
    # 1. URL concurrency: process up to 300 websites simultaneously for network checks (HTTP, DNS, SSL)
    concurrency_limit = min(settings.max_concurrent_scans, 300)
    url_semaphore = asyncio.Semaphore(concurrency_limit)
    # 2. Screenshot concurrency: throttle Playwright Chromium instances (up to 20) to preserve RAM & CPU
    screenshot_limit = getattr(settings, "max_concurrent_screenshots", 20)
    screenshot_semaphore = asyncio.Semaphore(screenshot_limit)

    async def scan_single_url(raw_url: str):
        nonlocal completed
        if scan_id not in _running_tasks:
            return

        async with url_semaphore:
            if scan_id not in _running_tasks:
                return

            # Extract tentative domain for parallel DNS & SSL lookups
            try:
                parsed = urlparse(raw_url if "://" in raw_url else f"https://{raw_url}")
                tentative_domain = (parsed.netloc or parsed.path).split(":")[0].split("/")[0]
            except Exception:
                tentative_domain = raw_url.replace("https://", "").replace("http://", "").split("/")[0]

            # 1, 2, 3: Run HTTP Scan, DNS Analysis, and SSL Check concurrently in parallel!
            async def run_http():
                try:
                    return await http_scanner.scan_url(raw_url)
                except Exception as exc:
                    return {
                        "original_url": raw_url,
                        "final_url": raw_url,
                        "domain": tentative_domain,
                        "status": "OFFLINE",
                        "http_status_code": None,
                        "response_time_ms": None,
                        "server_info": None,
                        "website_title": None,
                        "error_message": str(exc),
                        "screenshot_path": None,
                    }

            async def run_dns():
                try:
                    res = await dns_analyzer.analyze(tentative_domain)
                    return res.get("records", [])
                except Exception:
                    return []

            async def run_ssl():
                try:
                    return await ssl_checker.check(tentative_domain)
                except Exception:
                    return None

            http_res, dns_records, ssl_data = await asyncio.gather(
                run_http(), run_dns(), run_ssl()
            )

            domain = http_res.get("domain") or tentative_domain

            # 4. Screenshot Capture (protected by screenshot semaphore)
            screenshot_path = None
            if http_res.get("status") in ("ONLINE", "HTTP_ERROR") or http_res.get("http_status_code"):
                try:
                    target_to_capture = http_res.get("final_url") or raw_url
                    async with screenshot_semaphore:
                        ss_res = await screenshot_capturer.capture(target_to_capture, scan_id)
                    if ss_res.get("success"):
                        screenshot_path = ss_res.get("screenshot_path")
                except Exception as ss_err:
                    logger.error("Screenshot error for %s: %s", raw_url, ss_err)

            http_res["screenshot_path"] = screenshot_path

            # Save result and sub-records to SQLite (thread-safe async db session)
            async with progress_lock:
                completed += 1
                async with get_db() as db:
                    result_id = await save_scan_result(db, scan_id=scan_id, result_data=http_res)
                    if dns_records:
                        await save_dns_records(db, scan_result_id=result_id, records_list=dns_records)
                    if ssl_data:
                        await save_ssl_details(db, scan_result_id=result_id, ssl_data=ssl_data)

                    # Update scan progress every 3 URLs or when fully completed
                    if completed % 3 == 0 or completed == total:
                        await update_scan_status(db, scan_id, "running", completed_urls=completed)

    try:
        # Run all URLs concurrently governed by the semaphore
        await asyncio.gather(*[scan_single_url(u) for u in urls])

        # Mark completed unless marked cancelled
        async with get_db() as db:
            scan_row = await get_scan(db, scan_id)
            if scan_row and scan_row.get("status") == "cancelled":
                pass
            else:
                await update_scan_status(db, scan_id, "completed", completed_urls=completed)

    except asyncio.CancelledError:
        async with get_db() as db:
            await update_scan_status(db, scan_id, "cancelled", completed_urls=completed)
    except Exception as exc:
        logger.error("Scan %s failed: %s", scan_id, exc, exc_info=True)
        async with get_db() as db:
            await update_scan_status(db, scan_id, "failed", completed_urls=completed)
    finally:
        try:
            await screenshot_capturer.cleanup()
        except Exception:
            pass
        _running_tasks.pop(scan_id, None)


# ---------------------------------------------------------------------------
# POST /api/scan
# ---------------------------------------------------------------------------
@router.post("/scan")
async def start_scan(request: Request):
    """
    Start a new scan.

    Accepts:
    - JSON payload: {"urls": ["..."]} or {"url": "..."}
    - Multipart form: field 'file' (.xlsx / .xls)
    """
    content_type = request.headers.get("content-type", "").lower()
    collected_urls: List[str] = []

    if "multipart/form-data" in content_type:
        form = await request.form()
        uploaded_file = form.get("file")
        if uploaded_file and hasattr(uploaded_file, "read"):
            contents = await uploaded_file.read()
            filename = getattr(uploaded_file, "filename", "") or ""
            collected_urls = _extract_urls_from_file(contents, filename)
        else:
            urls_val = form.getlist("urls") or form.get("urls")
            if isinstance(urls_val, list):
                collected_urls = [str(u).strip() for u in urls_val if str(u).strip()]
            elif urls_val:
                collected_urls = [str(urls_val).strip()]
    else:
        # JSON body
        try:
            body = await request.json()
        except Exception:
            body = {}

        if isinstance(body, dict):
            urls = body.get("urls")
            url = body.get("url")
            if urls and isinstance(urls, list):
                collected_urls = [str(u).strip() for u in urls if str(u).strip()]
            elif url and isinstance(url, str):
                collected_urls = [url.strip()]
        elif isinstance(body, list):
            collected_urls = [str(u).strip() for u in body if str(u).strip()]

    if not collected_urls:
        raise HTTPException(status_code=400, detail="No URLs provided.")

    # Auto-slice large lists to maximum batch capacity (e.g. 1000 targets)
    if len(collected_urls) > settings.max_urls_per_scan:
        logger.info(
            "Input contains %d URLs; auto-slicing to max allowed batch limit of %d URLs.",
            len(collected_urls),
            settings.max_urls_per_scan,
        )
        collected_urls = collected_urls[:settings.max_urls_per_scan]

    # Validate each URL
    validated: List[str] = []
    for u in collected_urls:
        try:
            norm_url = validate_url(u)
            if not is_safe_url(norm_url):
                raise HTTPException(status_code=400, detail=f"Target URL is not allowed: {u}")
            validated.append(norm_url)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid URL: {exc}")

    scan_id = str(uuid.uuid4())
    created_at = _now_iso()

    async with get_db() as db:
        await create_scan(db, scan_id=scan_id, total_urls=len(validated))

    # Launch background scan
    task = asyncio.create_task(_run_scan(scan_id, validated))
    _running_tasks[scan_id] = task

    return {
        "scan_id": scan_id,
        "status": "pending",
        "total_urls": len(validated),
        "created_at": created_at,
    }


# ---------------------------------------------------------------------------
# Overloaded POST /api/scan that also accepts a plain JSON body
# (FastAPI cannot mix UploadFile and a JSON body in the same function
#  signature; use a separate route that accepts the raw body.)
# ---------------------------------------------------------------------------
@router.post("/scan/json")
async def start_scan_json(payload: Dict[str, Any]):
    """
    JSON-only variant: ``{"urls": [...]}`` or ``{"url": "..."}``.
    """
    urls = payload.get("urls")
    url = payload.get("url")
    collected: List[str] = []

    if urls and isinstance(urls, list):
        collected = [u.strip() for u in urls if isinstance(u, str) and u.strip()]
    elif url and isinstance(url, str):
        collected = [url.strip()]

    if not collected:
        raise HTTPException(status_code=400, detail="No URLs provided.")

    if len(collected) > settings.max_urls_per_scan:
        logger.info(
            "Input contains %d URLs; auto-slicing to max allowed batch limit of %d URLs.",
            len(collected),
            settings.max_urls_per_scan,
        )
        collected = collected[:settings.max_urls_per_scan]

    validated: List[str] = []
    for u in collected:
        u = validate_url(u)
        if not is_safe_url(u):
            raise HTTPException(status_code=400, detail=f"URL is not allowed: {u}")
        validated.append(u)

    scan_id = str(uuid.uuid4())
    created_at = _now_iso()
    async with get_db() as db:
        await create_scan(db, scan_id=scan_id, urls=validated, created_at=created_at)

    task = asyncio.create_task(_run_scan(scan_id, validated))
    _running_tasks[scan_id] = task

    return {
        "scan_id": scan_id,
        "status": "pending",
        "total_urls": len(validated),
        "created_at": created_at,
    }


# ---------------------------------------------------------------------------
# GET /api/scan/{scan_id}
# ---------------------------------------------------------------------------
@router.get("/scan/{scan_id}")
async def get_scan_status(scan_id: str):
    async with get_db() as db:
        scan = await get_scan(db, scan_id)
    if scan is None:
        raise HTTPException(status_code=404, detail="Scan not found.")
    return scan


# ---------------------------------------------------------------------------
# GET /api/scan/{scan_id}/results
# ---------------------------------------------------------------------------
@router.get("/scan/{scan_id}/results")
async def get_scan_results_endpoint(scan_id: str):
    async with get_db() as db:
        scan = await get_scan(db, scan_id)
        if scan is None:
            raise HTTPException(status_code=404, detail="Scan not found.")
        results = await get_scan_results(db, scan_id)
    return results


# ---------------------------------------------------------------------------
# POST /api/scan/{scan_id}/cancel
# ---------------------------------------------------------------------------
@router.post("/scan/{scan_id}/cancel")
async def cancel_scan(scan_id: str):
    task = _running_tasks.get(scan_id)
    if task is None:
        raise HTTPException(status_code=404, detail="No running scan found with this ID.")
    task.cancel()
    _running_tasks.pop(scan_id, None)

    async with get_db() as db:
        await update_scan_status(db, scan_id, "cancelled")

    return {"scan_id": scan_id, "status": "cancelled"}


# ---------------------------------------------------------------------------
# GET /api/history
# ---------------------------------------------------------------------------
@router.get("/history")
async def scan_history(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    search: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
):
    async with get_db() as db:
        items = await get_scan_history(
            db, limit=limit, offset=offset, search=search, status_filter=status,
        )
        count_query = "SELECT COUNT(DISTINCT s.id) FROM scans s"
        clauses = []
        params = []
        if search:
            count_query += " LEFT JOIN scan_results sr ON sr.scan_id = s.id"
            clauses.append("sr.original_url LIKE ?")
            params.append(f"%{search}%")
        if status:
            clauses.append("s.status = ?")
            params.append(status)
        if clauses:
            count_query += " WHERE " + " AND ".join(clauses)
        cursor = await db.execute(count_query, params)
        total_row = await cursor.fetchone()
        total = total_row[0] if total_row else len(items)

    return {"items": items, "total": total}


# ---------------------------------------------------------------------------
# GET /api/screenshots
# ---------------------------------------------------------------------------
@router.get("/screenshots")
async def list_screenshots(limit: int = Query(60, ge=1, le=200)):
    """Return all captured screenshots across all scan results."""
    from backend.app.database.repository import _rows_to_dicts
    async with get_db() as db:
        cursor = await db.execute(
            """
            SELECT id, scan_id, original_url, final_url, domain, status,
                   http_status_code, response_time_ms, server_info, website_title,
                   screenshot_path, created_at
            FROM scan_results
            WHERE screenshot_path IS NOT NULL AND screenshot_path != ''
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
        rows = await cursor.fetchall()
        return _rows_to_dicts(rows)


# ---------------------------------------------------------------------------
# GET /api/dns/{domain}
# ---------------------------------------------------------------------------
@router.get("/dns/{domain}")
async def dns_lookup(domain: str):
    """Standalone DNS lookup for a single domain."""
    if ScanService is None:
        raise HTTPException(status_code=501, detail="ScanService is not available.")
    try:
        service = ScanService()
        records = await service.dns_lookup(domain)
        return {"domain": domain, "records": records}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# GET /api/ssl/{domain}
# ---------------------------------------------------------------------------
@router.get("/ssl/{domain}")
async def ssl_check(domain: str):
    """Standalone SSL certificate check for a single domain."""
    if ScanService is None:
        raise HTTPException(status_code=501, detail="ScanService is not available.")
    try:
        service = ScanService()
        details = await service.ssl_check(domain)
        return {"domain": domain, "ssl": details}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# GET /api/screenshots/{filename}
# ---------------------------------------------------------------------------
@router.get("/screenshots/{filename:path}")
async def serve_screenshot(filename: str):
    name = os.path.basename(filename)
    filepath = os.path.join(settings.screenshots_dir, name)
    if not os.path.isfile(filepath):
        raise HTTPException(status_code=404, detail="Screenshot not found.")
    return FileResponse(filepath, media_type="image/png")


# ---------------------------------------------------------------------------
# Global / Time-Range PDF & Excel Exports across ALL websites
# (Defined before /reports/{scan_id}/... to avoid path collision)
# ---------------------------------------------------------------------------

def _parse_time_range(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    preset: Optional[str] = None,
) -> tuple[Optional[str], Optional[str], str]:
    """Parse time range query parameters into SQL-compatible timestamps and a human label."""
    now = datetime.now(timezone.utc)
    if preset == "24h":
        start = now - timedelta(hours=24)
        return start.strftime("%Y-%m-%d %H:%M:%S"), now.strftime("%Y-%m-%d %H:%M:%S"), "Last 24 Hours"
    elif preset == "7d":
        start = now - timedelta(days=7)
        return start.strftime("%Y-%m-%d %H:%M:%S"), now.strftime("%Y-%m-%d %H:%M:%S"), "Last 7 Days"
    elif preset == "30d":
        start = now - timedelta(days=30)
        return start.strftime("%Y-%m-%d %H:%M:%S"), now.strftime("%Y-%m-%d %H:%M:%S"), "Last 30 Days"

    start_str = None
    end_str = None
    if start_date:
        start_str = start_date.replace("T", " ")
        if len(start_str) == 10:
            start_str += " 00:00:00"
    if end_date:
        end_str = end_date.replace("T", " ")
        if len(end_str) == 10:
            end_str += " 23:59:59"

    label = f"{start_str or 'All Past Audits'} to {end_str or 'Present'}"
    return start_str, end_str, label


@router.get("/reports/export/pdf")
async def export_time_range_pdf(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    preset: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
):
    """Generate and download a combined PDF report for all websites analyzed within a time range."""
    if PDFReportGenerator is None:
        raise HTTPException(status_code=501, detail="PDF report generator is unavailable.")

    start_str, end_str, label = _parse_time_range(start_date, end_date, preset)

    async with get_db() as db:
        results = await get_results_by_time_range(
            db, start_date=start_str, end_date=end_str, status_filter=status, limit=1000
        )

    if not results:
        raise HTTPException(status_code=404, detail="No website audits found within the selected time range.")

    scan_meta = {
        "id": f"time_range_{preset or 'custom'}_{int(time.time())}",
        "scan_id": f"range_{preset or 'custom'}",
        "created_at": f"{label} (Exported {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')})",
        "total_urls": len(results),
        "status": "completed",
    }

    timestamp = int(time.time())
    filename = f"WebPulse_FullAudit_{preset or 'range'}_{timestamp}.pdf"
    filepath = os.path.join(settings.reports_dir, filename)

    generator = PDFReportGenerator()
    await generator.generate(scan=scan_meta, results=results, output_path=filepath)

    return FileResponse(
        filepath,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/reports/export/excel")
async def export_time_range_excel(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    preset: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
):
    """Generate and download a combined 4-sheet Excel report for all websites analyzed within a time range."""
    if ExcelReportGenerator is None:
        raise HTTPException(status_code=501, detail="Excel report generator is unavailable.")

    start_str, end_str, label = _parse_time_range(start_date, end_date, preset)

    async with get_db() as db:
        results = await get_results_by_time_range(
            db, start_date=start_str, end_date=end_str, status_filter=status, limit=1000
        )

    if not results:
        raise HTTPException(status_code=404, detail="No website audits found within the selected time range.")

    scan_meta = {
        "id": f"time_range_{preset or 'custom'}_{int(time.time())}",
        "scan_id": f"range_{preset or 'custom'}",
        "created_at": f"{label} (Exported {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')})",
        "total_urls": len(results),
        "status": "completed",
    }

    timestamp = int(time.time())
    filename = f"WebPulse_FullAudit_{preset or 'range'}_{timestamp}.xlsx"
    filepath = os.path.join(settings.reports_dir, filename)

    generator = ExcelReportGenerator()
    await generator.generate(scan=scan_meta, results=results, output_path=filepath)

    return FileResponse(
        filepath,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# GET /api/reports/{scan_id}/pdf
# ---------------------------------------------------------------------------
@router.get("/reports/{scan_id}/pdf")
async def download_pdf_report(scan_id: str):
    if PDFReportGenerator is None:
        raise HTTPException(status_code=501, detail="PDF report generation is not available.")

    # Ensure the scan exists
    async with get_db() as db:
        scan = await get_scan(db, scan_id)
        if scan is None:
            raise HTTPException(status_code=404, detail="Scan not found.")
        results = await get_scan_results(db, scan_id)

    filename = f"report_{scan_id}.pdf"
    filepath = os.path.join(settings.reports_dir, filename)

    # Generate only if not cached
    if not os.path.isfile(filepath):
        generator = PDFReportGenerator()
        await generator.generate(scan=scan, results=results, output_path=filepath)

    return FileResponse(
        filepath,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# GET /api/reports/{scan_id}/excel
# ---------------------------------------------------------------------------
@router.get("/reports/{scan_id}/excel")
async def download_excel_report(scan_id: str):
    if ExcelReportGenerator is None:
        raise HTTPException(status_code=501, detail="Excel report generation is not available.")

    async with get_db() as db:
        scan = await get_scan(db, scan_id)
        if scan is None:
            raise HTTPException(status_code=404, detail="Scan not found.")
        results = await get_scan_results(db, scan_id)

    filename = f"report_{scan_id}.xlsx"
    filepath = os.path.join(settings.reports_dir, filename)

    if not os.path.isfile(filepath):
        generator = ExcelReportGenerator()
        await generator.generate(scan=scan, results=results, output_path=filepath)

    return FileResponse(
        filepath,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# GET /api/dashboard
# ---------------------------------------------------------------------------
@router.get("/dashboard")
async def dashboard():
    """Return aggregate dashboard statistics computed from actual scan data."""
    async with get_db() as db:
        stats = await get_dashboard_stats(db)
    return stats


# ---------------------------------------------------------------------------
# WebSocket /api/ws/scan/{scan_id}
# ---------------------------------------------------------------------------
@router.websocket("/ws/scan/{scan_id}")
async def ws_scan_progress(websocket: WebSocket, scan_id: str):
    """
    Stream scan progress updates to the client.

    The client connects and receives JSON messages of the form:
        {"scan_id": "...", "status": "...", "progress": 0.42, ...}

    The socket closes automatically when the scan reaches a terminal state
    (completed, failed, cancelled) or when the client disconnects.
    """
    await websocket.accept()
    try:
        while True:
            async with get_db() as db:
                scan = await get_scan(db, scan_id)

            if scan is None:
                await websocket.send_json({"error": "Scan not found."})
                break

            await websocket.send_json(scan)

            # Stop streaming once the scan has finished
            status = scan.get("status") if isinstance(scan, dict) else getattr(scan, "status", None)
            if status in ("completed", "failed", "cancelled"):
                break

            await asyncio.sleep(1)
    except WebSocketDisconnect:
        pass
    finally:
        try:
            await websocket.close()
        except RuntimeError:
            pass  # Already closed
