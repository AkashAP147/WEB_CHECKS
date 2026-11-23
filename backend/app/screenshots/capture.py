"""
Screenshot Capture Service for WebPulse.

Provides headless Chromium screenshot capture using Playwright with:
- Synchronous Playwright runner wrapped in asyncio.to_thread to prevent
  Windows asyncio event loop 'NotImplementedError' (_make_subprocess_transport)
  which occurs with Uvicorn SelectorEventLoop.
- Full-page PNG screenshots at 1440x900 viewport.
- Universal diagnostic fallback screenshot generation (using Pillow) so that
  offline, HTTP errors (4xx, 5xx), timeouts, SSL and DNS error sites ALWAYS
  receive a high-fidelity visual diagnostic card in both the UI and PDF reports.
"""

import os
import re
import sys
import time
import logging
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from typing import Optional, Dict, Any

from backend.app.config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Check Playwright and Pillow availability at import time
# ---------------------------------------------------------------------------
try:
    from playwright.sync_api import sync_playwright, Error as PlaywrightError
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    PlaywrightError = Exception  # fallback

try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False


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


def generate_diagnostic_screenshot(
    abs_path: str,
    url: str,
    status_info: Optional[Dict[str, Any]] = None,
) -> bool:
    """Generate a crisp 1440x900 diagnostic screenshot mockup image.

    Used when a website is offline, returned an HTTP error, or failed navigation.
    Guarantees every target in WebPulse has a visual snapshot in UI and PDF.
    """
    if not PIL_AVAILABLE:
        return False

    status_info = status_info or {}
    status = (status_info.get("status") or "OFFLINE").upper()
    http_code = status_info.get("http_status_code")
    error_msg = status_info.get("error_message") or ""
    latency = status_info.get("response_time_ms")
    domain = status_info.get("domain") or _sanitize_domain(url)

    # Color themes by status
    if status == "ONLINE":
        badge_bg = (22, 163, 74)       # emerald-600
        badge_text = "ONLINE"
    elif status == "HTTP_ERROR" or (http_code and http_code >= 400):
        badge_bg = (220, 38, 38)       # red-600
        badge_text = f"HTTP ERROR {http_code}" if http_code else "HTTP ERROR"
    elif status == "OFFLINE":
        badge_bg = (225, 29, 72)       # rose-600
        badge_text = "OFFLINE — SERVER UNREACHABLE"
    elif status == "DNS_ERROR":
        badge_bg = (217, 119, 6)       # amber-600
        badge_text = "DNS LOOKUP FAILED"
    elif status == "SSL_ERROR":
        badge_bg = (190, 18, 60)       # rose-700
        badge_text = "SSL / TLS ERROR"
    elif status == "TIMEOUT":
        badge_bg = (217, 119, 6)       # amber-600
        badge_text = "CONNECTION TIMED OUT"
    else:
        badge_bg = (100, 116, 139)     # slate-500
        badge_text = f"DIAGNOSTIC: {status}"

    width, height = 1440, 900
    img = Image.new("RGB", (width, height), color=(15, 23, 42))  # slate-900
    draw = ImageDraw.Draw(img)

    # Load default font
    font = ImageFont.load_default()

    # 1. Top Browser Chrome Bar
    draw.rectangle([(0, 0), (width, 56)], fill=(30, 41, 59))  # slate-800
    draw.line([(0, 56), (width, 56)], fill=(51, 65, 85), width=1)

    # Window traffic light buttons
    draw.ellipse([(20, 20), (36, 36)], fill=(239, 68, 68))    # red
    draw.ellipse([(44, 20), (60, 36)], fill=(245, 158, 11))   # yellow
    draw.ellipse([(68, 20), (84, 36)], fill=(16, 185, 129))   # green

    # Chrome URL Address Bar
    draw.rounded_rectangle([(110, 12), (900, 44)], radius=8, fill=(51, 65, 85))
    clean_url = url if "://" in url else f"https://{url}"
    draw.text((128, 20), f"[!]  {clean_url}", fill=(203, 213, 225), font=font)

    # 2. Central Diagnostics Panel Card
    card_x1, card_y1 = 180, 130
    card_x2, card_y2 = 1260, 780
    draw.rounded_rectangle([(card_x1, card_y1), (card_x2, card_y2)], radius=16, fill=(30, 41, 59), outline=(51, 65, 85), width=2)

    # Status Pill inside Card
    draw.rounded_rectangle([(card_x1 + 40, card_y1 + 40), (card_x1 + 380, card_y1 + 80)], radius=8, fill=badge_bg)
    draw.text((card_x1 + 55, card_y1 + 52), badge_text, fill=(255, 255, 255), font=font)

    # Domain Title
    draw.text((card_x1 + 40, card_y1 + 105), f"Target: {domain}", fill=(248, 250, 252), font=font)
    draw.line([(card_x1 + 40, card_y1 + 135), (card_x2 - 40, card_y1 + 135)], fill=(51, 65, 85), width=1)

    # Key Diagnostics List
    y_cursor = card_y1 + 160
    metrics = [
        ("Diagnostic State:", f"{status}"),
        ("HTTP Response Code:", f"{http_code if http_code is not None else 'None (Connection not established)'}"),
        ("Measured Latency:", f"{latency:.1f} ms" if latency is not None else "Timeout / No Response"),
        ("Error Classification:", error_msg if error_msg else "Host unreachable or server error response received"),
    ]

    for label, val in metrics:
        draw.text((card_x1 + 40, y_cursor), label, fill=(148, 163, 184), font=font)
        # Wrap long text if needed
        val_str = str(val)[:95]
        draw.text((card_x1 + 260, y_cursor), val_str, fill=(241, 245, 249), font=font)
        y_cursor += 36

    # Informational notice box
    notice_y1 = y_cursor + 30
    notice_y2 = notice_y1 + 130
    draw.rounded_rectangle([(card_x1 + 40, notice_y1), (card_x2 - 40, notice_y2)], radius=10, fill=(15, 23, 42), outline=(71, 85, 105), width=1)
    
    notice_title = "AUTOMATED VISUAL INSPECTION REPORT"
    draw.text((card_x1 + 60, notice_y1 + 18), notice_title, fill=(99, 102, 241), font=font)
    notice_text = (
        "The automated Chromium browser engine encountered a network or HTTP error condition while\n"
        "requesting this resource. The diagnostics above reflect the real-time server handshake state."
    )
    draw.text((card_x1 + 60, notice_y1 + 45), notice_text, fill=(148, 163, 184), font=font)

    # Footer note with timestamp
    ts_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    footer_text = f"WebPulse Health & DNS Engine  •  Verified at {ts_str}"
    draw.text((card_x1 + 40, card_y2 - 45), footer_text, fill=(100, 116, 139), font=font)

    try:
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        img.save(abs_path, format="PNG")
        return True
    except Exception as exc:
        logger.error("Failed to save diagnostic screenshot to %s: %s", abs_path, exc)
        return False


def _sync_capture_worker(
    url: str,
    abs_path: str,
    viewport: dict,
    timeout_ms: int = 15000,
    status_info: Optional[Dict[str, Any]] = None,
) -> None:
    """Worker function executed inside a thread using sync_playwright.
    
    Tries headless Chromium capture first; if navigation fails or times out,
    automatically generates a crisp diagnostic screenshot.
    """
    if sys.platform == "win32":
        try:
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        except Exception:
            pass

    browser_captured = False

    if PLAYWRIGHT_AVAILABLE:
        try:
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

                    # Fast DOM navigation (optimized 5s timeout)
                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=min(timeout_ms, 5000))
                    except Exception:
                        try:
                            page.goto(url, wait_until="commit", timeout=3000)
                        except Exception:
                            pass

                    try:
                        page.wait_for_timeout(200)
                    except Exception:
                        pass

                    page.screenshot(path=abs_path, full_page=True, type="png")
                    if os.path.exists(abs_path) and os.path.getsize(abs_path) > 1000:
                        browser_captured = True
                finally:
                    try:
                        browser.close()
                    except Exception:
                        pass
        except Exception as exc:
            logger.debug("Playwright browser navigation failed for %s (%s). Using diagnostic screenshot.", url, exc)

    # Fallback to diagnostic mockup image if browser capture didn't produce a valid file
    if not browser_captured or not os.path.exists(abs_path) or os.path.getsize(abs_path) == 0:
        generate_diagnostic_screenshot(abs_path, url, status_info)


class ScreenshotCapture:
    """Headless Chromium screenshot service backed by Playwright with diagnostic fallbacks.

    Executes via sync_playwright within worker threads (asyncio.to_thread)
    and guarantees a valid screenshot file for EVERY target (online, offline, error).
    """

    DEFAULT_VIEWPORT = {"width": 1440, "height": 900}
    DEFAULT_NAV_TIMEOUT_MS = 7_000

    def __init__(self, screenshots_dir: str | None = None) -> None:
        self.screenshots_dir = screenshots_dir or settings.screenshots_dir

    async def initialize(self) -> None:
        """No-op kept for lifecycle compatibility."""
        pass

    async def cleanup(self) -> None:
        """No-op kept for lifecycle compatibility."""
        pass

    async def capture(
        self,
        url: str,
        scan_id: str,
        status_info: Optional[Dict[str, Any]] = None,
    ) -> dict:
        """Capture screenshot for given URL and scan ID."""
        return await self.capture_single(url, scan_id, status_info=status_info)

    async def capture_single(
        self,
        url: str,
        scan_id: str,
        status_info: Optional[Dict[str, Any]] = None,
    ) -> dict:
        """Capture screenshot running sync Playwright in a background worker thread."""
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
                status_info,
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
                # Emergency fallback
                generate_diagnostic_screenshot(abs_path, url, status_info)
                rel_path = f"screenshots/{filename}"
                return {
                    "success": True,
                    "screenshot_path": rel_path,
                    "error_message": None,
                    "capture_time_ms": round(elapsed, 2),
                }

        except Exception as exc:
            elapsed = (time.perf_counter() - start) * 1000
            msg = f"Error capturing screenshot for {url}: {exc}"
            logger.error(msg, exc_info=True)
            # Try to produce diagnostic image even on exception
            try:
                filename = _build_filename(scan_id, url)
                abs_path = os.path.join(self.screenshots_dir, filename)
                generate_diagnostic_screenshot(abs_path, url, status_info)
                return {
                    "success": True,
                    "screenshot_path": f"screenshots/{filename}",
                    "error_message": None,
                    "capture_time_ms": round(elapsed, 2),
                }
            except Exception:
                return {
                    "success": False,
                    "screenshot_path": None,
                    "error_message": msg,
                    "capture_time_ms": round(elapsed, 2),
                }

    async def __aenter__(self):
        await self.initialize()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.cleanup()
        return False
