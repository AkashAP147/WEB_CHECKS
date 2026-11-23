"""
DNS Record Analyzer module for WebPulse.

Performs comprehensive DNS record lookups and analysis for a given domain,
including A, AAAA, CNAME, MX, NS, TXT, SOA, and CAA records. Extracts
SPF and DMARC policies, and provides structured results with per-lookup
timing and error handling.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any, Optional
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Attempt to import dns.asyncresolver; fall back to sync resolver if needed.
# ---------------------------------------------------------------------------
try:
    import dns.asyncresolver

    _HAS_ASYNC_RESOLVER = True
except ImportError:
    _HAS_ASYNC_RESOLVER = False

import dns.exception
import dns.name
import dns.rdatatype
import dns.resolver

# Record types to query for the target domain.
_RECORD_TYPES: list[str] = ["A", "AAAA", "CNAME", "MX", "NS", "TXT", "SOA", "CAA"]


def extract_domain(url: str) -> str:
    """Extract the domain (hostname) from a URL or bare domain string.

    Handles:
      - Full URLs with scheme (``http://``, ``https://``, etc.)
      - URLs without a scheme (e.g. ``example.com/path``)
      - Hostnames with ports (``example.com:8080``)
      - IDN / internationalized domain names
      - Sub-domains (``sub.example.com``)

    Returns the bare hostname in lower-case, stripped of any trailing dot.
    """

    url = url.strip()

    # If there is no scheme, urlparse may treat the first path component as
    # the netloc, so we prepend a scheme when one is missing.
    if "://" not in url:
        url = f"https://{url}"

    parsed = urlparse(url)
    hostname: str = parsed.hostname or parsed.netloc or ""

    # Remove trailing dot that some DNS utilities append.
    hostname = hostname.rstrip(".").lower()

    return hostname


class DNSAnalyzer:
    """Asynchronous DNS record analyzer.

    Usage::

        analyzer = DNSAnalyzer()
        result = await analyzer.analyze("example.com")
    """

    # Default per-query timeout and lifetime (seconds optimized for fast parallel batches).
    DEFAULT_TIMEOUT: float = 2.0
    DEFAULT_LIFETIME: float = 4.0

    def __init__(
        self,
        timeout: float = DEFAULT_TIMEOUT,
        lifetime: float = DEFAULT_LIFETIME,
    ) -> None:
        self.timeout = timeout
        self.lifetime = lifetime

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def analyze(self, domain: str) -> dict[str, Any]:
        """Run a full DNS audit for *domain* and return structured results.

        Parameters
        ----------
        domain:
            A domain name **or** URL.  If a URL is passed it will be
            normalised via :func:`extract_domain`.

        Returns
        -------
        dict with keys:
            records            – list of per-type result dicts
            resolved_ipv4      – list[str]
            resolved_ipv6      – list[str]
            nameservers        – list[str]
            mail_servers       – list[str]
            spf_record         – str | None
            dmarc_record       – str | None
            cname_aliases      – list[str]
            total_lookup_time_ms – float
            has_errors         – bool
        """

        domain = extract_domain(domain)

        overall_start = time.perf_counter()

        # Launch all record-type lookups concurrently.
        tasks = {
            rtype: asyncio.ensure_future(self._lookup(domain, rtype))
            for rtype in _RECORD_TYPES
        }

        # Also fetch DMARC (TXT at _dmarc.<domain>) concurrently.
        dmarc_task = asyncio.ensure_future(
            self._lookup(f"_dmarc.{domain}", "TXT")
        )

        # Await everything.
        results_by_type: dict[str, dict[str, Any]] = {}
        for rtype, task in tasks.items():
            results_by_type[rtype] = await task

        dmarc_result: dict[str, Any] = await dmarc_task

        total_lookup_time_ms = (time.perf_counter() - overall_start) * 1000.0

        # ----- Aggregate -------------------------------------------------
        records: list[dict[str, Any]] = []
        has_errors = False

        for rtype in _RECORD_TYPES:
            entry = results_by_type[rtype]
            records.extend(entry["records"])
            if entry["status"] == "error":
                has_errors = True

        # Convenience collections ------------------------------------------
        resolved_ipv4 = self._values_for(results_by_type, "A")
        resolved_ipv6 = self._values_for(results_by_type, "AAAA")
        nameservers = self._values_for(results_by_type, "NS")
        mail_servers = self._values_for(results_by_type, "MX")
        cname_aliases = self._values_for(results_by_type, "CNAME")

        # SPF – found inside TXT records.
        spf_record: Optional[str] = None
        for rec in results_by_type["TXT"]["records"]:
            val: str = rec["record_value"]
            if val.lower().startswith("v=spf1"):
                spf_record = val
                break

        # DMARC – found in _dmarc.<domain> TXT lookup.
        dmarc_record: Optional[str] = None
        for rec in dmarc_result["records"]:
            val = rec["record_value"]
            if val.lower().startswith("v=dmarc1"):
                dmarc_record = val
                break

        return {
            "records": records,
            "resolved_ipv4": resolved_ipv4,
            "resolved_ipv6": resolved_ipv6,
            "nameservers": nameservers,
            "mail_servers": mail_servers,
            "spf_record": spf_record,
            "dmarc_record": dmarc_record,
            "cname_aliases": cname_aliases,
            "total_lookup_time_ms": round(total_lookup_time_ms, 2),
            "has_errors": has_errors,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _lookup(
        self, domain: str, rtype: str
    ) -> dict[str, Any]:
        """Query DNS for *rtype* records of *domain*.

        Returns a dict with ``records`` (list), ``status`` (str), and
        ``lookup_time_ms`` (float).
        """

        start = time.perf_counter()
        records: list[dict[str, Any]] = []
        status = "success"
        error_message: Optional[str] = None

        try:
            answer = await self._resolve(domain, rtype)
            for rdata in answer:
                records.append(
                    {
                        "record_type": rtype,
                        "record_value": self._format_rdata(rtype, rdata),
                        "ttl": int(answer.rrset.ttl) if answer.rrset else 0,
                        "lookup_status": "success",
                        "error_message": None,
                        "lookup_time_ms": 0.0,  # patched below
                    }
                )
        except (dns.resolver.NoAnswer, dns.resolver.NXDOMAIN) as exc:
            # The record type simply does not exist – not an error.
            status = "not_found"
            error_message = str(exc)
        except dns.resolver.NoNameservers as exc:
            status = "error"
            error_message = f"NoNameservers: {exc}"
        except dns.exception.Timeout as exc:
            status = "error"
            error_message = f"Timeout: {exc}"
        except dns.exception.DNSException as exc:
            status = "error"
            error_message = f"DNSException: {exc}"
        except Exception as exc:  # pragma: no cover – safety net
            status = "error"
            error_message = f"Unexpected: {exc}"

        elapsed_ms = round((time.perf_counter() - start) * 1000.0, 2)

        # If no records were collected (not_found / error), emit a single
        # summary entry so callers always have something to inspect.
        if not records:
            records.append(
                {
                    "record_type": rtype,
                    "record_value": None,
                    "ttl": None,
                    "lookup_status": status,
                    "error_message": error_message,
                    "lookup_time_ms": elapsed_ms,
                }
            )
        else:
            # Stamp timing onto every record produced by a successful lookup.
            for rec in records:
                rec["lookup_time_ms"] = elapsed_ms

        return {
            "records": records,
            "status": status,
            "lookup_time_ms": elapsed_ms,
        }

    async def _resolve(
        self, domain: str, rtype: str
    ) -> dns.resolver.Answer:
        """Resolve *domain* / *rtype*, using the async resolver when available."""

        if _HAS_ASYNC_RESOLVER:
            resolver = dns.asyncresolver.Resolver()
            resolver.timeout = self.timeout
            resolver.lifetime = self.lifetime
            return await resolver.resolve(domain, rtype)

        # Fallback: wrap the synchronous resolver in a thread so the
        # caller can still ``await`` it without blocking the event loop.
        def _sync_resolve() -> dns.resolver.Answer:
            resolver = dns.resolver.Resolver()
            resolver.timeout = self.timeout
            resolver.lifetime = self.lifetime
            return resolver.resolve(domain, rtype)

        return await asyncio.to_thread(_sync_resolve)

    # ------------------------------------------------------------------
    # Formatting helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_rdata(rtype: str, rdata: Any) -> str:
        """Return a human-friendly string representation of *rdata*."""

        if rtype == "MX":
            # "priority hostname"
            return f"{rdata.preference} {rdata.exchange.to_text().rstrip('.')}"

        if rtype == "SOA":
            # "mname rname serial refresh retry expire minimum"
            return (
                f"{rdata.mname.to_text().rstrip('.')} "
                f"{rdata.rname.to_text().rstrip('.')} "
                f"{rdata.serial} {rdata.refresh} {rdata.retry} "
                f"{rdata.expire} {rdata.minimum}"
            )

        if rtype == "TXT":
            # TXT rdata may consist of multiple strings; join them.
            return "".join(
                s.decode("utf-8", errors="replace")
                if isinstance(s, bytes)
                else str(s)
                for s in rdata.strings
            )

        if rtype == "CAA":
            return f'{rdata.flags} {rdata.tag} "{rdata.value}"'

        if rtype == "NS":
            return rdata.to_text().rstrip(".")

        if rtype == "CNAME":
            return rdata.to_text().rstrip(".")

        # A, AAAA, and anything else – the default text form.
        return rdata.to_text().rstrip(".")

    @staticmethod
    def _values_for(
        results: dict[str, dict[str, Any]], rtype: str
    ) -> list[str]:
        """Collect the ``record_value`` strings for *rtype* from *results*."""

        return [
            rec["record_value"]
            for rec in results.get(rtype, {}).get("records", [])
            if rec["record_value"] is not None
        ]
