"""
WebPulse - Pydantic schemas for scans, DNS records, SSL details, and dashboard.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------

class ScanRequest(BaseModel):
    """Accept either a list of URLs or a single URL string."""
    urls: list[str] = Field(default_factory=list, description="List of URLs to scan")
    url: Optional[str] = Field(default=None, description="Single URL to scan (convenience)")

    @field_validator("urls", mode="before")
    @classmethod
    def _coerce_urls(cls, v):
        if isinstance(v, str):
            return [v]
        return v

    def get_urls(self) -> list[str]:
        """Return the consolidated, deduplicated list of URLs."""
        combined = list(self.urls)
        if self.url and self.url not in combined:
            combined.append(self.url)
        return combined


# ---------------------------------------------------------------------------
# Response / result schemas
# ---------------------------------------------------------------------------

class ScanResponse(BaseModel):
    """Returned when a new scan is created."""
    scan_id: str
    status: str
    created_at: datetime
    total_urls: int


class ScanResultSchema(BaseModel):
    """Mirrors the scan_results table."""
    id: int
    scan_id: str
    original_url: str
    final_url: Optional[str] = None
    domain: Optional[str] = None
    status: str
    http_status_code: Optional[int] = None
    response_time_ms: Optional[float] = None
    server_info: Optional[str] = None
    website_title: Optional[str] = None
    screenshot_path: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime

    # Nested records (populated on demand)
    dns_records: list[DNSRecordSchema] = Field(default_factory=list)
    ssl_details: Optional[SSLDetailSchema] = None


class DNSRecordSchema(BaseModel):
    """Mirrors the dns_records table."""
    id: int
    scan_result_id: int
    domain: str
    record_type: str
    record_value: Optional[str] = None
    ttl: Optional[int] = None
    lookup_status: Optional[str] = None
    error_message: Optional[str] = None
    lookup_time_ms: Optional[float] = None


class SSLDetailSchema(BaseModel):
    """Mirrors the ssl_details table."""
    id: int
    scan_result_id: int
    domain: str
    issuer: Optional[str] = None
    subject: Optional[str] = None
    valid_from: Optional[datetime] = None
    expiry_date: Optional[datetime] = None
    remaining_days: Optional[int] = None
    hostname_match: Optional[bool] = None
    https_available: Optional[bool] = None
    verification_status: Optional[str] = None
    error_message: Optional[str] = None


# Forward-ref update so ScanResultSchema can reference the above
ScanResultSchema.model_rebuild()


class ScanProgress(BaseModel):
    """Live progress of an in-flight or completed scan."""
    scan_id: str
    status: str
    total_urls: int
    completed_urls: int
    progress_pct: float
    results: list[ScanResultSchema] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# History & dashboard schemas
# ---------------------------------------------------------------------------

class ScanHistoryItem(BaseModel):
    """Summary row shown in scan-history lists."""
    scan_id: str
    created_at: datetime
    total_urls: int
    online_count: int = 0
    offline_count: int = 0
    dns_errors: int = 0
    ssl_issues: int = 0
    status: str


class DashboardStats(BaseModel):
    """Aggregate stats for the dashboard overview."""
    total_scanned: int = 0
    online_count: int = 0
    offline_count: int = 0
    dns_errors: int = 0
    ssl_issues: int = 0
    avg_response_time: Optional[float] = None
    recent_scans: list[ScanHistoryItem] = Field(default_factory=list)
