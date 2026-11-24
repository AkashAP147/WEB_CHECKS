"""
URL validation and SSRF protection for WebPulse.

Provides URL normalization, private/reserved IP blocking, DNS-based SSRF
checks, redirect target revalidation, and Excel URL extraction.
"""

import ipaddress
import re
import socket
import csv
from io import BytesIO, StringIO
from urllib.parse import urlparse, urlunparse

import openpyxl
try:
    import xlrd
except ImportError:
    xlrd = None

# ---------------------------------------------------------------------------
# Private / reserved networks to block (SSRF protection)
# ---------------------------------------------------------------------------
BLOCKED_NETWORKS = [
    ipaddress.ip_network("127.0.0.0/8"),       # Loopback
    ipaddress.ip_network("10.0.0.0/8"),        # Private A
    ipaddress.ip_network("172.16.0.0/12"),     # Private B
    ipaddress.ip_network("192.168.0.0/16"),    # Private C
    ipaddress.ip_network("169.254.0.0/16"),    # Link-local (includes metadata)
    ipaddress.ip_network("0.0.0.0/32"),        # Unspecified
    ipaddress.ip_network("::1/128"),           # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),          # IPv6 unique-local
    ipaddress.ip_network("fe80::/10"),         # IPv6 link-local
]

# Cloud metadata hostnames that must be blocked regardless of resolved IP.
BLOCKED_HOSTNAMES = {
    "169.254.169.254",
    "metadata.google.internal",
    "metadata.google.internal.",
}

# Allowed URL schemes.
ALLOWED_SCHEMES = {"http", "https"}

# Simple pattern to reject obviously bogus hostnames.
_HOSTNAME_RE = re.compile(
    r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+"
    r"[a-zA-Z]{2,63}$"
    r"|^(?:\d{1,3}\.){3}\d{1,3}$"            # IPv4 literal
    r"|^\[[:0-9a-fA-F]+\]$",                  # IPv6 literal in brackets
    re.ASCII,
)


# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------

def validate_url(url: str) -> str:
    """Normalize and validate *url*.

    * Strips whitespace.
    * Prepends ``https://`` when no scheme is present.
    * Rejects schemes other than ``http`` / ``https``.
    * Rejects URLs without a valid hostname.

    Returns the normalized URL string.

    Raises:
        ValueError: If the URL is malformed or uses a disallowed scheme.
    """
    if not url or not isinstance(url, str):
        raise ValueError("URL must be a non-empty string.")

    url = url.strip()

    # Add scheme when missing.
    if not re.match(r"^https?://", url, re.IGNORECASE):
        # Handle "://" with a bad scheme, e.g. "ftp://..."
        if "://" in url:
            scheme = url.split("://", 1)[0].lower()
            if scheme not in ALLOWED_SCHEMES:
                raise ValueError(f"Scheme '{scheme}' is not allowed. Use http or https.")
        else:
            url = f"https://{url}"

    parsed = urlparse(url)

    if parsed.scheme.lower() not in ALLOWED_SCHEMES:
        raise ValueError(
            f"Scheme '{parsed.scheme}' is not allowed. Use http or https."
        )

    hostname = parsed.hostname
    if not hostname:
        raise ValueError("URL must contain a valid hostname.")

    # Basic hostname sanity (allow IPs and regular domains).
    if not _HOSTNAME_RE.match(hostname) and not _is_ip_literal(hostname):
        raise ValueError(f"Invalid hostname: {hostname}")

    # Rebuild with lowered scheme/host for consistency.
    normalized = urlunparse((
        parsed.scheme.lower(),
        parsed.netloc.lower(),
        parsed.path or "/",
        parsed.params,
        parsed.query,
        parsed.fragment,
    ))

    return normalized


def is_safe_url(url: str) -> bool:
    """Return ``True`` if *url* does **not** point at a blocked target.

    Checks the hostname against the blocked-hostname list and, when the
    hostname is an IP literal, against the blocked network ranges.

    .. note::
        This does **not** perform DNS resolution — use
        :func:`resolve_and_check` for a full SSRF guard.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False

    hostname = parsed.hostname
    if not hostname:
        return False

    # Block known metadata hostnames.
    if hostname.lower().rstrip(".") in BLOCKED_HOSTNAMES:
        return False

    # If hostname is an IP literal, check against blocked ranges.
    if _is_ip_literal(hostname):
        return _is_ip_safe(hostname)

    return True


def resolve_and_check(url: str) -> tuple[bool, str | None]:
    """Resolve the hostname in *url* via DNS and verify every returned IP.

    Returns (is_safe, error_reason):
    - (True, None) if safe.
    - (False, "BLOCKED") if targets loopback/private/internal IP or metadata.
    - (False, "DNS_ERROR") if hostname could not be resolved.
    """
    try:
        parsed = urlparse(url)
    except Exception:
        return False, "BLOCKED"

    hostname = parsed.hostname
    if not hostname:
        return False, "BLOCKED"

    # First run the cheap hostname-level check.
    if not is_safe_url(url):
        return False, "BLOCKED"

    try:
        infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
    except socket.gaierror:
        # Domain name does not resolve
        return False, "DNS_ERROR"
    except Exception:
        return False, "DNS_ERROR"

    for family, _type, _proto, _canonname, sockaddr in infos:
        ip_str = sockaddr[0]
        if not _is_ip_safe(ip_str):
            return False, "BLOCKED"

    return True, None


def validate_redirect_target(url: str) -> bool:
    """Revalidate a URL encountered during redirect following.

    Checks syntax and ensures the target does not point to internal metadata/private IPs.
    Returns ``True`` if the redirect target is safe.
    """
    try:
        normalized = validate_url(url)
    except ValueError:
        return False

    return is_safe_url(normalized)


# Regex to match valid domains or full URLs anywhere inside text
DOMAIN_OR_URL_REGEX = re.compile(
    r'(?:https?://)?(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,}(?:/[^\s,;"\'<>]*)?',
    re.IGNORECASE,
)

EXCLUDED_EXTENSIONS = {
    '.png', '.jpg', '.jpeg', '.gif', '.svg', '.webp', '.pdf',
    '.xlsx', '.xls', '.csv', '.zip', '.tar', '.gz', '.json',
    '.xml', '.txt', '.mp4', '.mp3'
}


def _extract_candidates_from_cell(val: object) -> list[str]:
    """Scan cell content (including embedded CSV lines) for valid URLs or domains."""
    if val is None:
        return []
    text = str(val).strip()
    if not text:
        return []

    found: list[str] = []

    # If cell has commas or tabs (e.g. raw CSV line pasted into one cell)
    if "," in text or "\t" in text:
        try:
            reader = csv.reader(StringIO(text))
            for row in reader:
                for c in row:
                    cand = c.strip().strip('"\'')
                    if cand and not re.match(r'^\d+(\.\d+)?$', cand):
                        for m in DOMAIN_OR_URL_REGEX.finditer(cand):
                            matched = m.group(0).strip('"\'').rstrip('.,;:')
                            if not re.match(r'^\d+\.\d+$', matched):
                                lower = matched.lower()
                                if not any(lower.endswith(ext) for ext in EXCLUDED_EXTENSIONS):
                                    found.append(matched)
        except Exception:
            pass

    # Direct regex search across cell text
    if not found:
        for m in DOMAIN_OR_URL_REGEX.finditer(text):
            matched = m.group(0).strip('"\'').rstrip('.,;:')
            if not re.match(r'^\d+\.\d+$', matched):
                lower = matched.lower()
                if not any(lower.endswith(ext) for ext in EXCLUDED_EXTENSIONS):
                    found.append(matched)

    return found


def validate_file_urls(file_bytes: bytes, filename: str = "") -> list[str]:
    """Parse a spreadsheet or text file (.xlsx, .xls, .csv) and extract URLs.

    * Scans all columns and rows across the active sheet or CSV
    * Handles raw CSV strings embedded inside a single cell (e.g. 1,"google.com",10)
    * Handles URLs located in column 2, column 3, or any position
    * Automatically skips IDs, numbers, and headers
    * Normalizes each URL via validate_url()

    Returns a list of deduplicated, normalized, validated URL strings.
    """
    fname = filename.lower()
    raw_candidates: list[str] = []

    # 1. Try XLSX (All columns and rows)
    if fname.endswith(".xlsx") or file_bytes.startswith(b"PK\x03\x04"):
        try:
            wb = openpyxl.load_workbook(BytesIO(file_bytes), read_only=True, data_only=True)
            ws = wb.active
            if ws is not None:
                for row in ws.iter_rows(values_only=True):
                    for cell in row:
                        raw_candidates.extend(_extract_candidates_from_cell(cell))
            wb.close()
        except Exception:
            pass

    # 2. Try XLS (Excel 97-2003 - All columns and rows)
    if not raw_candidates and (fname.endswith(".xls") or file_bytes.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")):
        if xlrd is not None:
            try:
                book = xlrd.open_workbook(file_contents=file_bytes)
                sheet = book.sheet_by_index(0)
                for r in range(sheet.nrows):
                    for c in range(sheet.ncols):
                        raw_candidates.extend(_extract_candidates_from_cell(sheet.cell_value(r, c)))
            except Exception:
                pass

    # 3. Try CSV / Text (All columns and rows)
    if not raw_candidates:
        for enc in ("utf-8-sig", "utf-8", "latin-1"):
            try:
                text = file_bytes.decode(enc)
                reader = csv.reader(StringIO(text))
                for row in reader:
                    for cell in row:
                        raw_candidates.extend(_extract_candidates_from_cell(cell))
                if raw_candidates:
                    break
            except Exception:
                continue

    if not raw_candidates:
        raise ValueError("Could not extract any URLs from the uploaded file. Please ensure it is a valid .csv, .xls, or .xlsx file.")

    # Deduplicate while preserving order and validating
    validated: list[str] = []
    seen: set[str] = set()

    for raw in raw_candidates:
        try:
            norm = validate_url(raw)
            if norm not in seen:
                seen.add(norm)
                validated.append(norm)
        except ValueError:
            continue

    if not validated:
        raise ValueError("No valid website URLs could be identified in the uploaded file.")

    return validated


def validate_excel_file(file_bytes: bytes, filename: str = "") -> list[str]:
    """Backwards-compatible alias for validate_file_urls."""
    return validate_file_urls(file_bytes, filename)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _is_ip_literal(hostname: str) -> bool:
    """Return ``True`` if *hostname* is a valid IPv4 or IPv6 address."""
    try:
        ipaddress.ip_address(hostname)
        return True
    except ValueError:
        return False


def _is_ip_safe(ip_str: str) -> bool:
    """Return ``True`` if *ip_str* is **not** in any blocked network."""
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return False

    for network in BLOCKED_NETWORKS:
        if addr in network:
            return False

    return True
