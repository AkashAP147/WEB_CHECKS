"""
WebPulse – API routes.

All endpoints are prefixed with /api via the router.
"""

from __future__ import annotations

import asyncio
import io
import os
import sys
import time
import uuid
from urllib.parse import urlparse
from datetime import datetime, timezone, timedelta
import logging
from typing import Any, Dict, List, Optional

import httpx

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
    get_recent_cached_result,
)
from backend.app.utils.url_validator import validate_url, is_safe_url, validate_excel_file
from backend.app.scanners.http_scanner import HttpScanner
from backend.app.dns.analyzer import DNSAnalyzer
from backend.app.ssl_mod.checker import SSLChecker
from backend.app.screenshots.capture import (
    ScreenshotCapture,
    generate_diagnostic_screenshot,
    _build_filename,
)

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
    """High-throughput asynchronous scan engine.

    Architecture:
    - Shared persistent HTTPX connection pool (up to 500 keep-alive connections).
    - Producer-Consumer asynchronous DB batch queue: workers never wait on SQLite locks.
    - Smart screenshot dispatch: live Chromium for ONLINE sites; instantaneous 0-overhead
      diagnostic cards for offline/error sites.
    - Non-blocking parallel workers with dual concurrency semaphores.
    - 24-hour deduplication cache: instant reuse with zero network re-scanning.
    """
    completed = 0
    total = len(urls)
    db_queue: asyncio.Queue = asyncio.Queue(maxsize=4000)
    writer_task: Optional[asyncio.Task] = None
    screenshot_capturer: Optional[ScreenshotCapture] = None

    try:
        http_scanner = HttpScanner()
        dns_analyzer = DNSAnalyzer()
        ssl_checker = SSLChecker()
        screenshot_capturer = ScreenshotCapture(settings.screenshots_dir)

        # 1. Update status to running immediately
        async with get_db() as db:
            await update_scan_status(db, scan_id, "running", completed_urls=0)

        # Domain-level fast in-memory caches (eliminates duplicate DNS/SSL checks for identical domains)
        _dns_memory_cache: Dict[str, list] = {}
        _ssl_memory_cache: Dict[str, dict | None] = {}

        # Concurrency control:
        # 1. URL network worker concurrency: 50 on Windows (75 on Linux/Colab) for high-speed scanning
        default_concurrency = 50 if sys.platform == "win32" else 75
        concurrency_limit = min(settings.max_concurrent_scans, default_concurrency)
        url_semaphore = asyncio.Semaphore(concurrency_limit)

        # 2. Screenshot concurrency: 4 to prevent CPU starvation on 2-vCPU Colab & Windows
        screenshot_limit = 4
        screenshot_semaphore = asyncio.Semaphore(screenshot_limit)

        # -----------------------------------------------------------------------
        # Producer-Consumer DB Batch Writer
        # -----------------------------------------------------------------------
        async def db_batch_writer():
            nonlocal completed
            stop_requested = False
            while not stop_requested:
                item = await db_queue.get()
                if item is None:
                    db_queue.task_done()
                    break

                batch = [item]
                while len(batch) < 25:
                    try:
                        extra = db_queue.get_nowait()
                        if extra is None:
                            stop_requested = True
                            db_queue.task_done()
                            break
                        batch.append(extra)
                    except asyncio.QueueEmpty:
                        break

                try:
                    async with get_db() as db:
                        for h_res, d_recs, s_dat in batch:
                            res_id = await save_scan_result(db, scan_id=scan_id, result_data=h_res, commit=False)
                            if d_recs:
                                await save_dns_records(db, scan_result_id=res_id, records_list=d_recs, commit=False)
                            if s_dat:
                                await save_ssl_details(db, scan_result_id=res_id, ssl_data=s_dat, commit=False)
                            completed += 1

                        # Single fast atomic commit for all 50 items in the batch
                        await db.commit()
                        # Immediate scan progress update on every batch write
                        await update_scan_status(db, scan_id, "running", completed_urls=completed)
                except Exception as write_err:
                    logger.error("DB batch write error: %s", write_err)
                finally:
                    for _ in batch:
                        db_queue.task_done()

        writer_task = asyncio.create_task(db_batch_writer())

        # -----------------------------------------------------------------------
        # Worker Coroutine
        # -----------------------------------------------------------------------
        async def scan_single_url(raw_url: str, client: httpx.AsyncClient):
            if scan_id not in _running_tasks:
                return

            try:
                parsed = urlparse(raw_url if "://" in raw_url else f"https://{raw_url}")
                tentative_domain = (parsed.netloc or parsed.path).split(":")[0].split("/")[0]
            except Exception:
                tentative_domain = raw_url.replace("https://", "").replace("http://", "").split("/")[0]

            # Coroutines for network operations:
            async def run_http():
                try:
                    return await asyncio.wait_for(
                        http_scanner.scan_url(raw_url, client=client),
                        timeout=12.0,
                    )
                except asyncio.TimeoutError:
                    return {
                        "original_url": raw_url,
                        "final_url": raw_url,
                        "domain": tentative_domain,
                        "status": "OFFLINE",
                        "http_status_code": None,
                        "response_time_ms": 12000.0,
                        "server_info": None,
                        "website_title": None,
                        "error_message": "Host unreachable (connection timed out after 12 seconds).",
                        "screenshot_path": None,
                    }
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
                if tentative_domain in _dns_memory_cache:
                    return _dns_memory_cache[tentative_domain]
                try:
                    res = await asyncio.wait_for(
                        dns_analyzer.analyze(tentative_domain),
                        timeout=5.0,
                    )
                    recs = res.get("records", [])
                    _dns_memory_cache[tentative_domain] = recs
                    return recs
                except Exception:
                    return []

            async def run_ssl():
                if tentative_domain in _ssl_memory_cache:
                    return _ssl_memory_cache[tentative_domain]
                try:
                    res = await asyncio.wait_for(
                        ssl_checker.check(tentative_domain),
                        timeout=5.0,
                    )
                    _ssl_memory_cache[tentative_domain] = res
                    return res
                except Exception:
                    return None

            # --- PHASE 1: FAST NETWORK AUDIT (Holds url_semaphore ONLY during network I/O) ---
            async with url_semaphore:
                if scan_id not in _running_tasks:
                    return

                http_res = await run_http()

                # If site redirected to another location, consider it ONLINE
                if http_res.get("is_redirect") or (http_res.get("final_url") and http_res.get("final_url").rstrip('/') != raw_url.rstrip('/')):
                    http_res["status"] = "ONLINE"

                status = http_res.get("status")
                target_to_capture = http_res.get("final_url") or raw_url

                # Only short-circuit DNS_ERROR (domain does not exist in DNS)
                if status == "DNS_ERROR":
                    try:
                        filename = _build_filename(scan_id, target_to_capture)
                        abs_path = os.path.join(settings.screenshots_dir, filename)
                        created = await asyncio.to_thread(
                            generate_diagnostic_screenshot, abs_path, target_to_capture, http_res
                        )
                        if created:
                            http_res["screenshot_path"] = f"screenshots/{filename}"
                    except Exception:
                        pass
                    await db_queue.put((http_res, [], None))
                    return

                # For ONLINE sites: run DNS and SSL concurrently
                if status == "ONLINE":
                    dns_records, ssl_data = await asyncio.gather(run_dns(), run_ssl())
                else:
                    dns_records, ssl_data = [], None

            # url_semaphore IS RELEASED! Other network workers immediately scan the next URLs!

            # --- PHASE 2: PARALLEL SCREENSHOT & BROWSER VERIFICATION DISPATCH ---
            screenshot_path = None
            try:
                async with screenshot_semaphore:
                    ss_res = await asyncio.wait_for(
                        screenshot_capturer.capture(
                            target_to_capture,
                            scan_id,
                            status_info=http_res,
                        ),
                        timeout=28.0,
                    )
                if ss_res.get("success"):
                    screenshot_path = ss_res.get("screenshot_path")
                    # If Chromium successfully navigated and captured the live page, upgrade to ONLINE
                    if ss_res.get("browser_captured"):
                        http_res["status"] = "ONLINE"
                        if ss_res.get("final_url"):
                            http_res["final_url"] = ss_res["final_url"]
                        if ss_res.get("title") and not http_res.get("website_title"):
                            http_res["website_title"] = ss_res["title"]
                        if not http_res.get("http_status_code"):
                            http_res["http_status_code"] = 200
                        http_res["error_message"] = None
            except Exception as ss_err:
                logger.debug("Screenshot error for %s: %s", raw_url, ss_err)

            # Fallback diagnostic snapshot if browser screenshot failed
            if not screenshot_path:
                try:
                    filename = _build_filename(scan_id, target_to_capture)
                    abs_path = os.path.join(settings.screenshots_dir, filename)
                    # Only create diagnostic image if a valid screenshot wasn't already written
                    if not os.path.exists(abs_path) or os.path.getsize(abs_path) == 0:
                        created = await asyncio.to_thread(
                            generate_diagnostic_screenshot, abs_path, target_to_capture, http_res
                        )
                        if created:
                            screenshot_path = f"screenshots/{filename}"
                    else:
                        screenshot_path = f"screenshots/{filename}"
                except Exception:
                    pass

            http_res["screenshot_path"] = screenshot_path

            # Push to DB batch queue (non-blocking instant hand-off)
            await db_queue.put((http_res, dns_records, ssl_data))

        # Main Scan Execution Loop with Shared High-Throughput Persistent HTTP Client
        limits = httpx.Limits(max_connections=500, max_keepalive_connections=250)
        async with httpx.AsyncClient(
            limits=limits,
            timeout=httpx.Timeout(connect=3.5, read=10.0, write=5.0, pool=None),
            follow_redirects=False,
            verify=False,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                )
            },
        ) as shared_client:
            await asyncio.gather(*[scan_single_url(u, shared_client) for u in urls])

        # Signal DB writer that all scanning is complete and wait for final flush with timeout
        try:
            await asyncio.wait_for(db_queue.put(None), timeout=5.0)
        except Exception:
            try:
                db_queue.put_nowait(None)
            except Exception:
                pass
        if writer_task and not writer_task.done():
            try:
                await asyncio.wait_for(writer_task, timeout=10.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                writer_task.cancel()

        # Mark scan completed in database
        async with get_db() as db:
            scan_row = await get_scan(db, scan_id)
            if scan_row and scan_row.get("status") == "cancelled":
                pass
            else:
                await update_scan_status(db, scan_id, "completed", completed_urls=completed)

    except asyncio.CancelledError:
        logger.info("Scan %s cancelled by user.", scan_id)
        try:
            db_queue.put_nowait(None)
        except Exception:
            pass
        if writer_task and not writer_task.done():
            try:
                await asyncio.wait_for(writer_task, timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                writer_task.cancel()
        try:
            async with get_db() as db:
                await update_scan_status(db, scan_id, "cancelled", completed_urls=completed)
        except Exception:
            pass
    except Exception as exc:
        logger.error("Scan %s failed with unexpected exception: %s", scan_id, exc, exc_info=True)
        try:
            db_queue.put_nowait(None)
        except Exception:
            pass
        if writer_task and not writer_task.done():
            try:
                await asyncio.wait_for(writer_task, timeout=5.0)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                writer_task.cancel()
        try:
            async with get_db() as db:
                await update_scan_status(db, scan_id, "failed", completed_urls=completed)
        except Exception:
            pass
    finally:
        if screenshot_capturer:
            try:
                await asyncio.wait_for(screenshot_capturer.cleanup(), timeout=10.0)
            except Exception as ss_clean_err:
                logger.debug("Screenshot cleanup error for %s: %s", scan_id, ss_clean_err)
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

    try:
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
    except Exception as exc:
        logger.error("Error reading scan request payload: %s", exc)
        raise HTTPException(status_code=400, detail=f"Failed to parse request payload: {exc}")

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

    # Validate each URL gracefully (skip headers, blank rows, or unparseable text)
    validated: List[str] = []
    for u in collected_urls:
        try:
            norm_url = validate_url(u)
            if is_safe_url(norm_url):
                validated.append(norm_url)
        except Exception:
            continue

    if not validated:
        raise HTTPException(status_code=400, detail="No valid URLs found in submission.")

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
        await create_scan(db, scan_id=scan_id, total_urls=len(validated))

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
# POST /api/scan/{scan_id}/cancel and /stop
# ---------------------------------------------------------------------------
@router.post("/scan/{scan_id}/cancel")
@router.post("/scan/{scan_id}/stop")
async def cancel_scan(scan_id: str):
    task = _running_tasks.get(scan_id)
    if task is not None:
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
async def download_pdf_report(
    scan_id: str,
    refresh: bool = Query(False),
    batch: Optional[int] = Query(None),
    batch_size: int = Query(1000),
    status: Optional[str] = Query(None, description="Filter: ALL, ONLINE, OFFLINE, ERRORS"),
    mode: Optional[str] = Query(None, description="Mode: summary, visual, issues"),
):
    if PDFReportGenerator is None:
        raise HTTPException(status_code=501, detail="PDF report generation is not available.")

    # Ensure the scan exists
    async with get_db() as db:
        scan = await get_scan(db, scan_id)
        if scan is None:
            raise HTTPException(status_code=404, detail="Scan not found.")
        results = await get_scan_results(db, scan_id)

    # Filter by mode if issues requested
    if mode == "issues" and not status:
        status = "ERRORS"

    # Filter by status if requested
    filtered_results = results
    status_suffix = ""
    if status and status.upper() != "ALL":
        sf = status.strip().upper()
        status_suffix = f"_{sf.lower()}"
        if sf == "ONLINE":
            filtered_results = [r for r in results if str(r.get("status") or "").upper() == "ONLINE"]
        elif sf == "OFFLINE":
            filtered_results = [r for r in results if str(r.get("status") or "").upper() == "OFFLINE"]
        elif sf in ("ERRORS", "ERROR", "WARNINGS"):
            filtered_results = [r for r in results if str(r.get("status") or "").upper() not in ("ONLINE", "OFFLINE")]

    # Support batched PDF slices (default 1000 targets per batch)
    batch_suffix = ""
    if batch is not None and batch > 0:
        start_idx = (batch - 1) * batch_size
        end_idx = min(start_idx + batch_size, len(filtered_results))
        batch_results = filtered_results[start_idx:end_idx]
        batch_suffix = f"_batch_{batch}"
    elif mode == "visual" and len(filtered_results) > batch_size:
        start_idx = 0
        end_idx = min(batch_size, len(filtered_results))
        batch_results = filtered_results[start_idx:end_idx]
        batch_suffix = "_batch_1"
    else:
        batch_results = filtered_results

    mode_suffix = f"_{mode}" if mode else ""
    filename = f"WebPulse_Audit_{scan_id[:8]}{status_suffix}{mode_suffix}{batch_suffix}.pdf"
    filepath = os.path.join(settings.reports_dir, filename)

    # Always generate or regenerate when requested, filtered, or if missing
    generator = PDFReportGenerator()
    await generator.generate(
        scan=scan,
        results=batch_results,
        output_path=filepath,
        status_filter=status,
        report_mode=mode,
    )

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
# GET /api/reports/{scan_id}/csv (Google Sheets & Excel Instant Export)
# ---------------------------------------------------------------------------
@router.get("/reports/{scan_id}/csv")
async def download_csv_report(scan_id: str):
    """Instant CSV report export compatible with Google Sheets and Excel."""
    import csv

    async with get_db() as db:
        scan = await get_scan(db, scan_id)
        if scan is None:
            raise HTTPException(status_code=404, detail="Scan not found.")
        results = await get_scan_results(db, scan_id)

    filename = f"WebPulse_GoogleSheets_{scan_id}.csv"
    filepath = os.path.join(settings.reports_dir, filename)

    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Domain",
            "Status",
            "HTTP Status Code",
            "Response Time (ms)",
            "Original Target URL",
            "Final / Redirect URL",
            "Web Server",
            "Website Title",
            "SSL Certificate Status",
            "DNS Status",
            "Diagnostic Error Details",
            "Audit Timestamp",
        ])
        for r in results:
            status = r.get("status", "UNKNOWN")
            ssl_status = "Valid" if status not in ("SSL_ERROR", "OFFLINE") else "Issue"
            dns_status = "Resolved" if status != "DNS_ERROR" else "Failed"
            writer.writerow([
                r.get("domain") or "",
                status,
                r.get("http_status_code") or "",
                round(r.get("response_time_ms") or 0, 1) if r.get("response_time_ms") is not None else "",
                r.get("original_url") or "",
                r.get("final_url") or "",
                r.get("server_info") or "",
                r.get("website_title") or "",
                ssl_status,
                dns_status,
                r.get("error_message") or "",
                r.get("created_at") or "",
            ])

    return FileResponse(
        filepath,
        media_type="text/csv",
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
