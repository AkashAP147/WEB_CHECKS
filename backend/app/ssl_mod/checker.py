"""SSL Certificate Checker module for WebPulse.

Provides :class:`SSLChecker` which asynchronously retrieves and validates
SSL/TLS certificates for a given domain and port, returning a comprehensive
result dictionary that never raises – every error path is captured gracefully.
"""

from __future__ import annotations

import asyncio
import hashlib
import ssl
import socket
from datetime import datetime, timezone
from typing import Any, Dict, Optional

try:
    import certifi
except ImportError:
    certifi = None

try:
    from cryptography import x509
    from cryptography.hazmat.backends import default_backend
    CRYPTOGRAPHY_AVAILABLE = True
except ImportError:
    CRYPTOGRAPHY_AVAILABLE = False


class SSLChecker:
    """Asynchronous SSL certificate checker.

    Usage::

        checker = SSLChecker()
        result = await checker.check("example.com")
    """

    DEFAULT_TIMEOUT: float = 3.5  # seconds (fast fail for parallel scans)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def check(self, domain: str, port: int = 443) -> Dict[str, Any]:
        """Check the SSL certificate for *domain*:*port*.

        Always returns a result dict – never raises.
        """
        result = self._empty_result(domain, port)

        # 1. Try a **verified** connection first (the happy path).
        verified_cert, verified_proto, verified_err = await self._fetch_cert(
            domain, port, verify=True
        )

        if verified_cert is not None:
            # Verified connection succeeded – certificate is trusted and
            # hostname matches.
            self._populate_from_cert(result, verified_cert, domain)
            result["https_available"] = True
            result["hostname_match"] = True
            result["protocol_version"] = verified_proto

            # Even though verification passed, the cert could still be
            # technically expired / not-yet-valid (clock skew corner case).
            self._set_verification_status(result, domain, trusted=True)
            return result

        # 2. Verified connection failed – try **unverified** to retrieve
        #    certificate details anyway (self-signed, expired, etc.).
        unverified_cert, unverified_proto, unverified_err = await self._fetch_cert(
            domain, port, verify=False
        )

        if unverified_cert is not None:
            self._populate_from_cert(result, unverified_cert, domain)
            result["https_available"] = True
            result["protocol_version"] = unverified_proto

            # Determine why the verified connection failed.
            self._set_verification_status(
                result,
                domain,
                trusted=False,
                verified_error=verified_err,
            )
            return result

        # 3. Both connections failed – no SSL/TLS at all.
        result["https_available"] = False
        result["verification_status"] = "error"
        result["error_message"] = self._friendly_error(
            verified_err or unverified_err
        )
        return result

    # ------------------------------------------------------------------
    # Certificate fetching helpers
    # ------------------------------------------------------------------

    async def _fetch_cert(
        self,
        domain: str,
        port: int,
        *,
        verify: bool,
    ) -> tuple[Optional[Dict[str, Any]], Optional[str], Optional[Exception]]:
        """Return ``(cert_dict, protocol_version, error)``."""
        try:
            cert, proto = await asyncio.wait_for(
                self._connect_and_get_cert(domain, port, verify=verify),
                timeout=self.DEFAULT_TIMEOUT,
            )
            return cert, proto, None
        except Exception as exc:  # noqa: BLE001
            return None, None, exc

    async def _connect_and_get_cert(
        self,
        domain: str,
        port: int,
        *,
        verify: bool,
    ) -> tuple[Dict[str, Any], str]:
        """Open an SSL connection and return the peer certificate dict and
        the negotiated protocol version string.

        Uses :func:`asyncio.to_thread` to offload the blocking handshake.
        """

        def _blocking() -> tuple[Dict[str, Any], str]:
            if certifi is not None:
                ctx = ssl.create_default_context(cafile=certifi.where())
            else:
                ctx = ssl.create_default_context()

            if not verify:
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE

            with socket.create_connection((domain, port), timeout=self.DEFAULT_TIMEOUT) as sock:
                with ctx.wrap_socket(sock, server_hostname=domain) as ssock:
                    cert = ssock.getpeercert(binary_form=False)
                    if not cert:
                        # When verify_mode is CERT_NONE, getpeercert() may
                        # return an empty dict. Fall back to the DER form.
                        der = ssock.getpeercert(binary_form=True)
                        if der:
                            cert = self._parse_der_cert(der)
                        else:
                            raise ssl.SSLError("No certificate received")
                    proto = ssock.version() or "unknown"
                    if "serialNumber" not in cert:
                        der = ssock.getpeercert(binary_form=True)
                        if der:
                            cert["_serial_from_der"] = self._serial_from_der(der)
                    return cert, proto

        return await asyncio.to_thread(_blocking)

    # ------------------------------------------------------------------
    # Certificate parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_der_cert(der: bytes) -> Dict[str, Any]:
        """Parse DER certificate using cryptography library or fallback."""
        if CRYPTOGRAPHY_AVAILABLE:
            try:
                cert = x509.load_der_x509_certificate(der, default_backend())
                # Extract subject
                subject_list = []
                for attr in cert.subject:
                    subject_list.append(((attr.oid._name or "commonName", attr.value),))
                
                # Extract issuer
                issuer_list = []
                for attr in cert.issuer:
                    issuer_list.append(((attr.oid._name or "commonName", attr.value),))

                # Extract SANs
                sans = []
                try:
                    san_ext = cert.extensions.get_extension_for_oid(x509.ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
                    sans = [("DNS", name) for name in san_ext.value.get_values_for_type(x509.DNSName)]
                except Exception:
                    pass

                not_before = cert.not_valid_before_utc.strftime("%b %d %H:%M:%S %Y GMT")
                not_after = cert.not_valid_after_utc.strftime("%b %d %H:%M:%S %Y GMT")

                res: Dict[str, Any] = {
                    "subject": tuple(subject_list),
                    "issuer": tuple(issuer_list),
                    "notBefore": not_before,
                    "notAfter": not_after,
                    "serialNumber": hex(cert.serial_number)[2:].upper(),
                }
                if sans:
                    res["subjectAltName"] = tuple(sans)
                return res
            except Exception:
                pass

        try:
            return ssl._ssl._test_decode_cert(None)  # type: ignore[attr-defined]
        except Exception:
            pass
        return {}

    @staticmethod
    def _serial_from_der(der: bytes) -> str:
        """Derive a hex serial-like fingerprint from the DER bytes."""
        return hashlib.sha256(der).hexdigest()[:40].upper()

    @staticmethod
    def _extract_issuer(cert: Dict[str, Any]) -> str:
        """Return a human-readable issuer string."""
        issuer_tuples = cert.get("issuer", ())
        org = ""
        cn = ""
        for rdn in issuer_tuples:
            for attr_type, attr_value in rdn:
                if attr_type == "organizationName":
                    org = attr_value
                elif attr_type == "commonName":
                    cn = attr_value
        return org or cn or "Unknown Issuer"

    @staticmethod
    def _extract_subject(cert: Dict[str, Any]) -> str:
        """Return the subject as ``CN=<value>`` or the first SAN."""
        subject_tuples = cert.get("subject", ())
        for rdn in subject_tuples:
            for attr_type, attr_value in rdn:
                if attr_type == "commonName":
                    return f"CN={attr_value}"
        # Fallback: first Subject Alternative Name
        sans = cert.get("subjectAltName", ())
        for _type, value in sans:
            return f"CN={value}"
        return "Unknown"

    @staticmethod
    def _parse_cert_date(date_str: str) -> Optional[datetime]:
        """Parse the date strings returned by :pymethod:`ssl.SSLSocket.getpeercert`.

        The format is ``'%b %d %H:%M:%S %Y %Z'`` (e.g. ``'Jan  5 09:33:21 2023 GMT'``).
        """
        formats = (
            "%b %d %H:%M:%S %Y %Z",
            "%b  %d %H:%M:%S %Y %Z",
            "%Y%m%d%H%M%SZ",
        )
        for fmt in formats:
            try:
                dt = datetime.strptime(date_str.strip(), fmt)
                # Assume UTC if no tzinfo.
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt
            except ValueError:
                continue
        return None

    # ------------------------------------------------------------------
    # Result dict helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _empty_result(domain: str, port: int) -> Dict[str, Any]:
        return {
            "domain": domain,
            "port": port,
            "issuer": None,
            "subject": None,
            "valid_from": None,
            "expiry_date": None,
            "remaining_days": None,
            "hostname_match": False,
            "https_available": False,
            "verification_status": "error",
            "error_message": None,
            "protocol_version": None,
            "serial_number": None,
        }

    def _populate_from_cert(
        self,
        result: Dict[str, Any],
        cert: Dict[str, Any],
        domain: str,
    ) -> None:
        """Fill *result* with data extracted from the certificate dict."""
        result["issuer"] = self._extract_issuer(cert)
        result["subject"] = self._extract_subject(cert)

        not_before_str = cert.get("notBefore", "")
        not_after_str = cert.get("notAfter", "")

        not_before = self._parse_cert_date(not_before_str) if not_before_str else None
        not_after = self._parse_cert_date(not_after_str) if not_after_str else None

        result["valid_from"] = not_before.isoformat() if not_before else None
        result["expiry_date"] = not_after.isoformat() if not_after else None

        if not_after is not None:
            now = datetime.now(timezone.utc)
            delta = not_after - now
            result["remaining_days"] = max(delta.days, 0)
        else:
            result["remaining_days"] = None

        # Serial number
        serial = cert.get("serialNumber") or cert.get("_serial_from_der")
        result["serial_number"] = serial

        # Hostname match (check SANs and subject CN)
        result["hostname_match"] = self._hostname_matches(cert, domain)

    @staticmethod
    def _hostname_matches(cert: Dict[str, Any], domain: str) -> bool:
        """Check whether *domain* matches the certificate's CN or SANs."""
        try:
            ssl.match_hostname(cert, domain)  # type: ignore[attr-defined]
            return True
        except (ssl.CertificateError, ValueError, AttributeError):
            pass

        # Manual fallback (match_hostname removed in 3.12+)
        domain_lower = domain.lower()

        # Check SANs
        for _type, value in cert.get("subjectAltName", ()):
            if _type.lower() == "dns":
                if _match_domain(value.lower(), domain_lower):
                    return True

        # Check subject CN
        for rdn in cert.get("subject", ()):
            for attr_type, attr_value in rdn:
                if attr_type == "commonName":
                    if _match_domain(attr_value.lower(), domain_lower):
                        return True
        return False

    # ------------------------------------------------------------------
    # Verification status logic
    # ------------------------------------------------------------------

    def _set_verification_status(
        self,
        result: Dict[str, Any],
        domain: str,
        *,
        trusted: bool,
        verified_error: Optional[Exception] = None,
    ) -> None:
        """Determine the ``verification_status`` field."""
        now = datetime.now(timezone.utc)

        # Parse dates from result (already ISO strings).
        valid_from = (
            datetime.fromisoformat(result["valid_from"])
            if result["valid_from"]
            else None
        )
        expiry_date = (
            datetime.fromisoformat(result["expiry_date"])
            if result["expiry_date"]
            else None
        )

        # Expired?
        if expiry_date and expiry_date < now:
            result["verification_status"] = "expired"
            result["remaining_days"] = 0
            result["error_message"] = (
                f"Certificate expired on {result['expiry_date']}"
            )
            return

        # Not yet valid?
        if valid_from and valid_from > now:
            result["verification_status"] = "not_yet_valid"
            result["error_message"] = (
                f"Certificate not valid until {result['valid_from']}"
            )
            return

        # Hostname mismatch?
        if not result["hostname_match"]:
            result["verification_status"] = "hostname_mismatch"
            result["error_message"] = (
                f"Certificate subject does not match hostname '{domain}'"
            )
            return

        if trusted:
            result["verification_status"] = "valid"
            return

        # Not trusted – try to distinguish self-signed from other causes.
        err_str = str(verified_error) if verified_error else ""
        err_lower = err_str.lower()

        if "self" in err_lower and "signed" in err_lower:
            result["verification_status"] = "self_signed"
            result["error_message"] = "Certificate is self-signed"
        elif (
            "certificate verify failed" in err_lower
            or "unable to get local issuer" in err_lower
            or "unknown ca" in err_lower
        ):
            # Heuristic: if issuer == subject it's self-signed.
            if result["issuer"] and result["subject"]:
                issuer_cn = result["issuer"]
                subject_cn = (
                    result["subject"].replace("CN=", "") if result["subject"].startswith("CN=") else result["subject"]
                )
                if issuer_cn == subject_cn:
                    result["verification_status"] = "self_signed"
                    result["error_message"] = "Certificate is self-signed"
                    return
            result["verification_status"] = "untrusted"
            result["error_message"] = (
                f"Certificate chain is not trusted: {err_str}"
            )
        else:
            result["verification_status"] = "untrusted"
            result["error_message"] = err_str or "Certificate is not trusted"

    # ------------------------------------------------------------------
    # Misc helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _friendly_error(exc: Optional[Exception]) -> str:
        if exc is None:
            return "Unknown error"
        if isinstance(exc, asyncio.TimeoutError):
            return "Connection timed out"
        if isinstance(exc, ConnectionRefusedError):
            return "Connection refused – port may be closed"
        if isinstance(exc, socket.gaierror):
            return f"DNS resolution failed: {exc}"
        if isinstance(exc, ssl.SSLError):
            return f"SSL error: {exc}"
        if isinstance(exc, OSError):
            return f"Network error: {exc}"
        return f"Unexpected error: {exc}"


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------


def _match_domain(pattern: str, domain: str) -> bool:
    """Match a certificate DNS name *pattern* (which may contain a leading
    wildcard) against *domain*.

    Examples::

        _match_domain("*.example.com", "www.example.com")  # True
        _match_domain("example.com", "example.com")        # True
        _match_domain("*.example.com", "example.com")      # False
    """
    if pattern == domain:
        return True
    if pattern.startswith("*."):
        # Wildcard: must match exactly one label on the left.
        suffix = pattern[2:]
        # Domain must end with the suffix and have exactly one extra label.
        if domain.endswith("." + suffix):
            prefix = domain[: -(len(suffix) + 1)]
            if "." not in prefix:
                return True
    return False
