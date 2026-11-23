"""
HTTP availability scanner for WebPulse.

Uses ``httpx.AsyncClient`` with manual redirect following so that every
intermediate target can be checked for SSRF before the request is sent.
"""

from __future__ import annotations

import re
import time
import asyncio
from dataclasses import dataclass, field
from typing import Any, Optional

import httpx

from backend.app.utils.url_validator import (
    resolve_and_check,
    validate_redirect_target,
    validate_url,
)

# ---------------------------------------------------------------------------
# Status constants
# ---------------------------------------------------------------------------
STATUS_ONLINE = "ONLINE"
STATUS_HTTP_ERROR = "HTTP_ERROR"
STATUS_SSL_ERROR = "SSL_ERROR"
STATUS_DNS_ERROR = "DNS_ERROR"
STATUS_OFFLINE = "OFFLINE"
STATUS_TIMEOUT = "TIMEOUT"
STATUS_BLOCKED = "BLOCKED"
STATUS_SSRF_BLOCKED = "SSRF_BLOCKED"

# Max redirects we are willing to follow manually.
MAX_REDIRECTS = 5

# Default request timeout in seconds (optimized for fast parallel scanning).
DEFAULT_TIMEOUT = 15.0

# Regex to pull <title> from an HTML document.
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)

# Common browser-like User-Agent to avoid bot-blocks on casual scans.
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/122.0.0.0 Safari/537.36 "
    "WebPulse/1.0"
)


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------

@dataclass
class HttpScanner:
    """Async HTTP availability scanner.

    Parameters
    ----------
    timeout:
        Per-request timeout in seconds (default 7.0).
    """

    timeout: float = DEFAULT_TIMEOUT

    # ----- public API -------------------------------------------------------

    async def scan_url(self, url: str, client: Optional[httpx.AsyncClient] = None) -> dict[str, Any]:
        """Scan a single URL and return a comprehensive result dict.

        The result always contains the following keys:

        * ``original_url`` – the URL as supplied (after normalisation).
        * ``final_url`` – the URL after following redirects (may equal original).
        * ``domain`` – hostname extracted from *final_url*.
        * ``status`` – high-level status string (``ONLINE``, ``OFFLINE``, …).
        * ``http_status_code`` – integer HTTP status or ``None``.
        * ``response_time_ms`` – round-trip time in milliseconds or ``None``.
        * ``server_info`` – value of the ``Server`` response header or ``None``.
        * ``website_title`` – text content of the ``<title>`` tag or ``None``.
        * ``error_message`` – human-readable error string or ``None``.
        * ``redirect_chain`` – list of intermediate URLs (empty when no redirect).
        * ``is_redirect`` – ``True`` if any redirect was followed.
        """

        result: dict[str, Any] = {
            "original_url": url,
            "final_url": None,
            "domain": None,
            "status": None,
            "http_status_code": None,
            "response_time_ms": None,
            "server_info": None,
            "website_title": None,
            "error_message": None,
            "redirect_chain": [],
            "is_redirect": False,
        }

        # -- Validate & normalise --------------------------------------------
        try:
            url = validate_url(url)
            result["original_url"] = url
        except ValueError as exc:
            result["status"] = STATUS_BLOCKED
            result["error_message"] = f"Invalid URL: {exc}"
            return result

        # -- SSRF pre-flight (non-blocking in thread pool with 5s timeout) ---
        try:
            is_safe, block_reason = await asyncio.wait_for(
                asyncio.to_thread(resolve_and_check, url), timeout=5.0
            )
            if not is_safe:
                if block_reason == "DNS_ERROR":
                    result["status"] = STATUS_DNS_ERROR
                    result["error_message"] = "DNS resolution failed: unable to resolve domain name."
                else:
                    result["status"] = STATUS_BLOCKED
                    result["error_message"] = "SSRF Protection: Access to private, loopback, or internal addresses is blocked."
                return result
        except asyncio.TimeoutError:
            # If pre-flight DNS takes longer than 5s, let HTTP client attempt connection directly
            pass

        # -- Issue request with manual redirect following --------------------
        redirect_chain: list[str] = []
        current_url = url
        response: httpx.Response | None = None
        start = time.monotonic()

        async def _execute_with_client(http_client: httpx.AsyncClient):
            nonlocal response, current_url
            for _ in range(MAX_REDIRECTS + 1):
                response = await http_client.get(current_url)

                if response.is_redirect:
                    redirect_location = response.headers.get("location")
                    if not redirect_location:
                        break

                    # Resolve relative redirects.
                    redirect_location = str(response.url.join(redirect_location))

                    # SSRF check on redirect target.
                    if not validate_redirect_target(redirect_location):
                        elapsed = (time.monotonic() - start) * 1000
                        result["response_time_ms"] = round(elapsed, 2)
                        result["status"] = STATUS_SSRF_BLOCKED
                        result["error_message"] = f"Redirect target blocked (SSRF): {redirect_location}"
                        result["redirect_chain"] = redirect_chain
                        result["is_redirect"] = bool(redirect_chain)
                        return False

                    redirect_chain.append(current_url)
                    current_url = redirect_location
                else:
                    break
            return True

        try:
            if client is not None:
                if not await _execute_with_client(client):
                    return result
            else:
                async with httpx.AsyncClient(
                    timeout=httpx.Timeout(self.timeout),
                    follow_redirects=False,
                    verify=True,
                    headers={"User-Agent": _USER_AGENT},
                ) as local_client:
                    if not await _execute_with_client(local_client):
                        return result

            elapsed = (time.monotonic() - start) * 1000

        # -- Error classification --------------------------------------------
        except httpx.TimeoutException as exc:
            elapsed = (time.monotonic() - start) * 1000
            result["response_time_ms"] = round(elapsed, 2)
            result["status"] = STATUS_TIMEOUT
            result["error_message"] = f"Request timed out: {exc}"
            result["redirect_chain"] = redirect_chain
            result["is_redirect"] = bool(redirect_chain)
            return result

        except ssl_error if (ssl_error := _get_ssl_exception()) else ():  # type: ignore[misc]
            elapsed = (time.monotonic() - start) * 1000
            result["response_time_ms"] = round(elapsed, 2)
            result["status"] = STATUS_SSL_ERROR
            result["error_message"] = f"SSL error: {ssl_error}"
            result["redirect_chain"] = redirect_chain
            result["is_redirect"] = bool(redirect_chain)
            return result

        except Exception as exc:
            elapsed = (time.monotonic() - start) * 1000
            result["response_time_ms"] = round(elapsed, 2)
            result["redirect_chain"] = redirect_chain
            result["is_redirect"] = bool(redirect_chain)
            result["status"], result["error_message"] = _classify_exception(exc)
            return result

        # -- Successful response — classify ----------------------------------
        if response is None:
            result["status"] = STATUS_OFFLINE
            result["error_message"] = "No response received."
            return result

        result["http_status_code"] = response.status_code
        result["response_time_ms"] = round(elapsed, 2)
        result["final_url"] = str(response.url) if not redirect_chain else current_url
        result["domain"] = httpx.URL(result["final_url"]).host
        result["server_info"] = response.headers.get("server")
        result["redirect_chain"] = redirect_chain
        result["is_redirect"] = bool(redirect_chain)

        # Attempt to extract page title from HTML responses.
        content_type = response.headers.get("content-type", "")
        if "text/html" in content_type:
            result["website_title"] = _extract_title(response.text)

        # Classify HTTP status code.
        code = response.status_code
        if 200 <= code < 300:
            result["status"] = STATUS_ONLINE
        elif 300 <= code < 400:
            # Redirect that wasn't followed further — still counts as online.
            result["status"] = STATUS_ONLINE
        elif code in (403, 404, 451):
            result["status"] = STATUS_HTTP_ERROR
            result["error_message"] = f"HTTP {code}: site is responding but returned an error."
        elif 500 <= code < 600:
            result["status"] = STATUS_HTTP_ERROR
            result["error_message"] = f"Server error: HTTP {code}"
        else:
            result["status"] = STATUS_HTTP_ERROR
            result["error_message"] = f"Unexpected HTTP status: {code}"

        return result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_title(html: str) -> str | None:
    """Return the ``<title>`` text from *html*, or ``None``."""
    match = _TITLE_RE.search(html[:8192])  # limit search window
    if match:
        title = match.group(1).strip()
        # Collapse whitespace.
        title = re.sub(r"\s+", " ", title)
        return title if title else None
    return None


def _classify_exception(exc: Exception) -> tuple[str, str]:
    """Map an ``httpx`` / stdlib exception to a ``(status, message)`` pair."""
    exc_type = type(exc).__name__
    exc_msg = str(exc)

    # DNS failure.
    if isinstance(exc, httpx.ConnectError):
        lower = exc_msg.lower()
        if "name or service not known" in lower or "getaddrinfo failed" in lower or "nodename nor servname" in lower:
            return STATUS_DNS_ERROR, f"DNS resolution failed: {exc_msg}"
        if "connection refused" in lower or "connection reset" in lower:
            return STATUS_OFFLINE, f"Connection refused/reset: {exc_msg}"
        return STATUS_OFFLINE, f"Connection error: {exc_msg}"

    if isinstance(exc, httpx.ConnectTimeout):
        return STATUS_TIMEOUT, f"Connection timed out: {exc_msg}"

    if isinstance(exc, httpx.ReadTimeout):
        return STATUS_TIMEOUT, f"Read timed out: {exc_msg}"

    # Catch-all.
    return STATUS_BLOCKED, f"{exc_type}: {exc_msg}"


def _get_ssl_exception():
    """Return the SSL exception class used by httpx if available, else None.

    httpx raises ``ssl.SSLError`` (wrapped inside ``httpx.ConnectError`` in
    newer versions), so we check for both.
    """
    try:
        import ssl as _ssl
        return _ssl.SSLError
    except ImportError:
        return None
