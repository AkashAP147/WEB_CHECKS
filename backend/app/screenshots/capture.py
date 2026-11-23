"""
Screenshot Capture Service for WebPulse.

Provides headless Chromium screenshot capture using Playwright with:
- Synchronous Playwright runner wrapped in asyncio.to_thread to prevent
  Windows asyncio event loop 'NotImplementedError' (_make_subprocess_transport)
  which occurs with Uvicorn SelectorEventLoop.
- Full-page PNG screenshots at 1440x900 viewport
- Graceful error handling for navigation failures, timeouts, and missing installs
"""

import os
import re
import sys
import time
import logging
import asyncio
from pathlib import Path
from urllib.parse import urlparse

from backend.app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Check Playwright availability at import time
# ---------------------------------------------------------------------------
try:
    from playwright.sync_api import sync_playwright, Error as PlaywrightError
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    PlaywrightError = Exception  # fallback


def _sanitize_domain(url: str) -> str:
    """Extract and sanitize domain from url for safe use in filenames."""
    try:
        parsed = urlparse(url if "://" in url else f"https://{url}")
        domain = parsed.netloc or parsed.path.split("/")[0]
    except Exception:
        domain = url
    domain = domain.split(":")[0]
    domain = re.sub(r"[^a-zA-Z0-9_-]", "_", domain)
    return domain or "unknown"


def _build_filename(scan_id: str, url: str) -> str:
    """Return a unique PNG filename: {scan_id}_{sanitized_domain}_{timestamp}.png"""
    domain = _sanitize_domain(url)
    timestamp = int(time.time() * 1000)
    return f"{scan_id}_{domain}_{timestamp}.png"


def _error_result(message: str, elapsed_ms: float = 0.0) -> dict:
    """Convenience helper for returning a failed-capture dict."""
    return {
        "success": False,
        "screenshot_path": None,
        "error_message": message,
        "capture_time_ms": round(elapsed_ms, 2),
    }


def _sync_capture_worker(
    url: str,
    abs_path: str,
    viewport: dict,
    timeout_ms: int = 25000,
) -> None:
    """Worker function executed inside a thread using sync_playwright.
    
    This completely isolates the browser subprocess management from Python's
    asyncio event loop, avoiding Windows SelectorEventLoop NotImplementedError.
    """
    if sys.platform == "win32":
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        except Exception:
            pass

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            context = browser.new_context(
                viewport=viewport,
                ignore_https_errors=True,
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36 WebPulse/1.0"
                ),
            )
            page = context.new_page()
            page.set_default_navigation_timeout(timeout_ms)

            # Fast DOM navigation
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=10000)
            except Exception:
                try:
                    page.goto(url, wait_until="commit", timeout=5000)
                except Exception:
                    pass  # Capture whatever content managed to render

            # Settle period for React / Vue / styles
            try:
                page.wait_for_timeout(500)
            except Exception:
                pass

            page.screenshot(path=abs_path, full_page=True, type="png")
        finally:
            try:
                browser.close()
            except Exception:
                pass


class ScreenshotCapture:
    """Headless Chromium screenshot service backed by Playwright.

    Executes via sync_playwright within worker threads (asyncio.to_thread)
    to guarantee 100% compatibility across all Windows asyncio event loop policies.
    """

    DEFAULT_VIEWPORT = {"width": 1440, "height": 900}
    DEFAULT_NAV_TIMEOUT_MS = 25_000

    def __init__(self, screenshots_dir: str | None = None) -> None:
        self.screenshots_dir = screenshots_dir or settings.screenshots_dir

    async def initialize(self) -> None:
        """No-op kept for lifecycle compatibility."""
        if not PLAYWRIGHT_AVAILABLE:
            raise RuntimeError(
                "Playwright is not installed. "
                "Run `pip install playwright && playwright install chromium`."
            )

    async def cleanup(self) -> None:
        """No-op kept for lifecycle compatibility."""
        pass

    async def capture(self, url: str, scan_id: str) -> dict:
        """Capture screenshot for given URL and scan ID."""
        return await self.capture_single(url, scan_id)

    async def capture_single(self, url: str, scan_id: str) -> dict:
        """Capture screenshot running sync Playwright in a background worker thread."""
        if not PLAYWRIGHT_AVAILABLE:
            return _error_result(
                "Playwright is not installed. "
                "Run `pip install playwright && playwright install chromium`."
            )

        start = time.perf_counter()
        try:
            # Ensure target directory exists
            Path(self.screenshots_dir).mkdir(parents=True, exist_ok=True)

            filename = _build_filename(scan_id, url)
            abs_path = os.path.join(self.screenshots_dir, filename)

            # Run in worker thread
            await asyncio.to_thread(
                _sync_capture_worker,
                url,
                abs_path,
                self.DEFAULT_VIEWPORT,
                self.DEFAULT_NAV_TIMEOUT_MS,
            )

            elapsed = (time.perf_counter() - start) * 1000

            if os.path.exists(abs_path) and os.path.getsize(abs_path) > 0:
                rel_path = f"screenshots/{filename}"
                logger.info("Screenshot successfully captured: %s (%.0f ms)", rel_path, elapsed)
                return {
                    "success": True,
                    "screenshot_path": rel_path,
                    "error_message": None,
                    "capture_time_ms": round(elapsed, 2),
                }
            else:
                return _error_result("Screenshot file was not generated or is empty.", elapsed)

        except PlaywrightError as exc:
            elapsed = (time.perf_counter() - start) * 1000
            msg = f"Playwright error for {url}: {exc}"
            logger.error(msg)
            return _error_result(msg, elapsed)

        except Exception as exc:
            elapsed = (time.perf_counter() - start) * 1000
            msg = f"Error capturing screenshot for {url}: {exc}"
            logger.error(msg, exc_info=True)
            return _error_result(msg, elapsed)

    async def __aenter__(self):
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.cleanup()
        return False
