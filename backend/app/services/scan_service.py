"""
Scan orchestration service for WebPulse.

Coordinates URL validation, HTTP scanning, DNS analysis, SSL checking, and
screenshot capture for a batch of URLs.  External modules (DNS, SSL,
screenshot) are imported lazily so the service works even if they are not
yet available.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any

from backend.app.scanners.http_scanner import HttpScanner
from backend.app.utils.url_validator import resolve_and_check, validate_url

# ---- Lazy / optional imports from other agents' modules --------------------
try:
    from backend.app.dns.analyzer import DNSAnalyzer
except ImportError:
    DNSAnalyzer = None

try:
    from backend.app.ssl_mod.checker import SSLChecker
except ImportError:
    SSLChecker = None

try:
    from backend.app.screenshots.capture import ScreenshotCapture
except ImportError:
    ScreenshotCapture = None

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MAX_CONCURRENCY = 5

SCAN_STATUS_PENDING = "pending"
SCAN_STATUS_RUNNING = "running"
SCAN_STATUS_COMPLETED = "completed"
SCAN_STATUS_CANCELLED = "cancelled"
SCAN_STATUS_FAILED = "failed"


# ---------------------------------------------------------------------------
# Scan service
# ---------------------------------------------------------------------------

class ScanService:
    """Orchestrates multi-URL scanning with concurrency control.

    Active scans are tracked internally so they can be cancelled at any
    time via :meth:`cancel_scan`.
    """

    def __init__(self) -> None:
        # scan_id -> asyncio.Event used to signal cancellation.
        self._active_scans: dict[str, asyncio.Event] = {}
        self._http_scanner = HttpScanner()

    # ----- public API -------------------------------------------------------

    async def start_scan(self, urls: list[str], db: Any) -> str:
        """Create a scan record in *db*, launch :meth:`run_scan` in the
        background, and return the ``scan_id`` immediately.

        Parameters
        ----------
        urls:
            Raw URL strings to scan.
        db:
            Database repository / session object (expected to expose
            ``create_scan``, ``update_scan``, ``create_scan_result``, and
            ``update_scan_result`` coroutines).
        """
        scan_id = str(uuid.uuid4())

        # Persist the scan header.
        await db.create_scan({
            "scan_id": scan_id,
            "status": SCAN_STATUS_PENDING,
            "total_urls": len(urls),
            "completed_urls": 0,
            "created_at": _now_iso(),
            "updated_at": _now_iso(),
        })

        # Register cancellation event and kick off work.
        cancel_event = asyncio.Event()
        self._active_scans[scan_id] = cancel_event

        asyncio.create_task(self._run_scan_wrapper(scan_id, urls, db, cancel_event))

        return scan_id

    async def cancel_scan(self, scan_id: str, db: Any) -> bool:
        """Request cancellation of an active scan.

        Returns ``True`` if the scan was found and cancellation was
        signalled, ``False`` otherwise.
        """
        cancel_event = self._active_scans.get(scan_id)
        if cancel_event is None:
            return False

        cancel_event.set()

        await db.update_scan(scan_id, {
            "status": SCAN_STATUS_CANCELLED,
            "updated_at": _now_iso(),
        })
        return True

    async def run_scan(self, scan_id: str, urls: list[str], db: Any) -> None:
        """Execute the full scan pipeline for every URL in *urls*.

        This is the main work-horse called internally by :meth:`start_scan`.
        It can also be invoked directly for testing.
        """
        cancel_event = self._active_scans.get(scan_id)
        if cancel_event is None:
            # Allow direct invocation without start_scan.
            cancel_event = asyncio.Event()
            self._active_scans[scan_id] = cancel_event

        # Mark scan as running.
        await db.update_scan(scan_id, {
            "status": SCAN_STATUS_RUNNING,
            "updated_at": _now_iso(),
        })

        semaphore = asyncio.Semaphore(MAX_CONCURRENCY)
        completed = 0
        total = len(urls)

        async def _process_url(raw_url: str) -> None:
            nonlocal completed

            if cancel_event.is_set():
                return

            async with semaphore:
                if cancel_event.is_set():
                    return

                result = await self._scan_single_url(raw_url, scan_id)

                # Persist individual result.
                try:
                    await db.create_scan_result({
                        "scan_id": scan_id,
                        "url": raw_url,
                        **result,
                        "scanned_at": _now_iso(),
                    })
                except Exception:
                    pass  # Don't let a DB error crash the batch.

                completed += 1

                # Update progress.
                try:
                    await db.update_scan(scan_id, {
                        "completed_urls": completed,
                        "updated_at": _now_iso(),
                    })
                except Exception:
                    pass

        # Fan-out tasks.
        tasks = [asyncio.create_task(_process_url(u)) for u in urls]
        await asyncio.gather(*tasks, return_exceptions=True)

        # Final status.
        final_status = (
            SCAN_STATUS_CANCELLED if cancel_event.is_set() else SCAN_STATUS_COMPLETED
        )
        await db.update_scan(scan_id, {
            "status": final_status,
            "completed_urls": completed,
            "updated_at": _now_iso(),
        })

        # Cleanup.
        self._active_scans.pop(scan_id, None)

    # ----- internal pipeline ------------------------------------------------

    async def _run_scan_wrapper(
        self,
        scan_id: str,
        urls: list[str],
        db: Any,
        cancel_event: asyncio.Event,
    ) -> None:
        """Wrapper around :meth:`run_scan` that catches unexpected crashes."""
        try:
            await self.run_scan(scan_id, urls, db)
        except Exception as exc:
            try:
                await db.update_scan(scan_id, {
                    "status": SCAN_STATUS_FAILED,
                    "error_message": str(exc),
                    "updated_at": _now_iso(),
                })
            except Exception:
                pass
            self._active_scans.pop(scan_id, None)

    async def _scan_single_url(self, raw_url: str, scan_id: str) -> dict[str, Any]:
        """Run the full check pipeline on a single URL.

        Steps: validate → HTTP scan → DNS lookup → SSL check → screenshot.

        Each step is wrapped in ``try / except`` so a failure in one does not
        prevent the others from running.
        """
        result: dict[str, Any] = {
            "http": None,
            "dns": None,
            "ssl": None,
            "screenshot": None,
        }

        # -- 1. Validate URL -------------------------------------------------
        try:
            normalized = validate_url(raw_url)
        except ValueError as exc:
            result["http"] = {
                "original_url": raw_url,
                "status": "BLOCKED",
                "error_message": f"Validation failed: {exc}",
            }
            return result

        # -- 2. SSRF pre-check -----------------------------------------------
        is_safe, block_reason = resolve_and_check(normalized)
        if not is_safe:
            result["http"] = {
                "original_url": raw_url,
                "status": "DNS_ERROR" if block_reason == "DNS_ERROR" else "BLOCKED",
                "error_message": "DNS resolution failed" if block_reason == "DNS_ERROR" else "SSRF Protection: URL resolves to a blocked/private address.",
            }
            return result

        # -- 3. HTTP scan (always available) ----------------------------------
        try:
            result["http"] = await self._http_scanner.scan_url(normalized)
        except Exception as exc:
            result["http"] = {
                "original_url": normalized,
                "status": "ERROR",
                "error_message": f"HTTP scan failed: {exc}",
            }

        # -- 4. DNS analysis (optional module) --------------------------------
        result["dns"] = await self._run_dns(normalized)

        # -- 5. SSL check (optional module) -----------------------------------
        result["ssl"] = await self._run_ssl(normalized)

        # -- 6. Screenshot (optional module) ----------------------------------
        result["screenshot"] = await self._run_screenshot(normalized)

        return result

    # ---- Optional module runners (graceful when missing) -------------------

    async def _run_dns(self, url: str) -> dict[str, Any] | None:
        """Run DNS analysis if the module is available."""
        if DNSAnalyzer is None:
            return None
        try:
            analyzer = DNSAnalyzer()
            if asyncio.iscoroutinefunction(getattr(analyzer, "analyze", None)):
                return await analyzer.analyze(url)
            return analyzer.analyze(url)
        except Exception as exc:
            return {"error": f"DNS analysis failed: {exc}"}

    async def _run_ssl(self, url: str) -> dict[str, Any] | None:
        """Run SSL check if the module is available."""
        if SSLChecker is None:
            return None
        try:
            checker = SSLChecker()
            if asyncio.iscoroutinefunction(getattr(checker, "check", None)):
                return await checker.check(url)
            return checker.check(url)
        except Exception as exc:
            return {"error": f"SSL check failed: {exc}"}

    async def _run_screenshot(self, url: str) -> dict[str, Any] | None:
        """Capture screenshot if the module is available."""
        if ScreenshotCapture is None:
            return None
        try:
            capture = ScreenshotCapture()
            if asyncio.iscoroutinefunction(getattr(capture, "capture", None)):
                return await capture.capture(url)
            return capture.capture(url)
        except Exception as exc:
            return {"error": f"Screenshot capture failed: {exc}"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()
