"""
WebPulse - Professional Excel Report Generator
Generates multi-sheet formatted Excel reports using OpenPyXL.
"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import openpyxl
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from backend.app.config import settings


class ExcelReportGenerator:
    """Generates corporate-grade Excel reports for WebPulse audits."""

    def __init__(self):
        # Color palette
        self.header_fill = PatternFill(start_color="1F4E79", end_color="1F4E79", fill_type="solid")
        self.sub_header_fill = PatternFill(start_color="2F5597", end_color="2F5597", fill_type="solid")
        self.alt_row_fill = PatternFill(start_color="F2F5F9", end_color="F2F5F9", fill_type="solid")
        self.card_header_fill = PatternFill(start_color="D9E1F2", end_color="D9E1F2", fill_type="solid")

        # Fonts
        self.header_font = Font(name="Calibri", size=11, bold=True, color="FFFFFF")
        self.title_font = Font(name="Calibri", size=16, bold=True, color="1F4E79")
        self.sub_title_font = Font(name="Calibri", size=11, italic=True, color="595959")
        self.bold_font = Font(name="Calibri", size=11, bold=True)
        self.regular_font = Font(name="Calibri", size=11)

        # Borders
        thin_border_side = Side(style="thin", color="D9D9D9")
        self.thin_border = Border(
            left=thin_border_side,
            right=thin_border_side,
            top=thin_border_side,
            bottom=thin_border_side,
        )
        self.header_border = Border(
            left=Side(style="thin", color="1B365D"),
            right=Side(style="thin", color="1B365D"),
            top=Side(style="medium", color="1B365D"),
            bottom=Side(style="medium", color="1B365D"),
        )

        # Alignments
        self.align_center = Alignment(horizontal="center", vertical="center")
        self.align_left = Alignment(horizontal="left", vertical="center")
        self.align_right = Alignment(horizontal="right", vertical="center")

    async def generate(
        self,
        scan: Dict[str, Any],
        results: List[Dict[str, Any]],
        output_path: str,
    ) -> str:
        """Create the 4-sheet Excel report and save to output_path."""
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        wb = openpyxl.Workbook()
        # Remove default sheet
        wb.remove(wb.active)

        # Fetch all DNS and SSL records in single batch queries (sub-millisecond)
        dns_records_by_site: List[Dict[str, Any]] = []
        ssl_details_by_site: List[Dict[str, Any]] = []
        scan_id = scan.get("id") or scan.get("scan_id")

        try:
            db_path = settings.db_path
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                if scan_id:
                    cur.execute(
                        """
                        SELECT d.* FROM dns_records d
                        JOIN scan_results r ON d.scan_result_id = r.id
                        WHERE r.scan_id = ?
                        """,
                        (scan_id,),
                    )
                    dns_records_by_site = [dict(r) for r in cur.fetchall()]

                    cur.execute(
                        """
                        SELECT s.* FROM ssl_details s
                        JOIN scan_results r ON s.scan_result_id = r.id
                        WHERE r.scan_id = ?
                        """,
                        (scan_id,),
                    )
                    ssl_details_by_site = [dict(r) for r in cur.fetchall()]
                elif results:
                    result_ids = [r["id"] for r in results if r.get("id")]
                    if result_ids:
                        placeholders = ",".join("?" for _ in result_ids)
                        cur.execute(f"SELECT * FROM dns_records WHERE scan_result_id IN ({placeholders})", result_ids)
                        dns_records_by_site = [dict(r) for r in cur.fetchall()]
                        cur.execute(f"SELECT * FROM ssl_details WHERE scan_result_id IN ({placeholders})", result_ids)
                        ssl_details_by_site = [dict(r) for r in cur.fetchall()]
        except Exception:
            pass

        # Build each sheet
        self._build_sheet_website_status(wb, results)
        self._build_sheet_dns_records(wb, dns_records_by_site)
        self._build_sheet_ssl_details(wb, ssl_details_by_site)
        self._build_sheet_summary(wb, scan, results)

        wb.save(output_path)
        return output_path

    def _build_sheet_website_status(self, wb: openpyxl.Workbook, results: List[Dict[str, Any]]):
        ws = wb.create_sheet(title="Website Status")
        ws.views.sheetView[0].showGridLines = True

        headers = [
            "Original URL",
            "Final URL",
            "Domain",
            "Status",
            "HTTP Status Code",
            "Response Time (ms)",
            "SSL Status",
            "DNS Status",
            "Website Title",
            "Scan Date",
            "Screenshot Filename",
            "Error Message",
        ]

        ws.append(headers)
        ws.freeze_panes = "A2"

        for row_idx, r in enumerate(results, start=2):
            status = r.get("status", "UNKNOWN")
            ssl_status = "Valid" if status not in ("SSL_ERROR", "OFFLINE") else "Issue"
            dns_status = "Resolved" if status != "DNS_ERROR" else "Failed"
            screenshot_fn = os.path.basename(r.get("screenshot_path") or "") if r.get("screenshot_path") else ""

            row_data = [
                r.get("original_url") or "",
                r.get("final_url") or "",
                r.get("domain") or "",
                status,
                r.get("http_status_code") or "",
                round(r.get("response_time_ms") or 0, 1) if r.get("response_time_ms") is not None else "",
                ssl_status,
                dns_status,
                r.get("website_title") or "",
                r.get("created_at") or "",
                screenshot_fn,
                r.get("error_message") or "",
            ]
            ws.append(row_data)

            # Style row cells
            fill = self.alt_row_fill if row_idx % 2 == 1 else None
            for col_idx in range(1, len(headers) + 1):
                cell = ws.cell(row=row_idx, column=col_idx)
                cell.font = self.regular_font
                cell.border = self.thin_border
                if fill:
                    cell.fill = fill
                if col_idx in (4, 5, 6, 7, 8, 10):
                    cell.alignment = self.align_center
                else:
                    cell.alignment = self.align_left

        self._style_header_row(ws, len(headers))
        self._add_conditional_formatting(ws, len(results), status_col="D")
        self._auto_fit_columns(ws)

    def _build_sheet_dns_records(self, wb: openpyxl.Workbook, records: List[Dict[str, Any]]):
        ws = wb.create_sheet(title="DNS Records")
        ws.views.sheetView[0].showGridLines = True

        headers = [
            "Domain",
            "Record Type",
            "Record Value",
            "TTL",
            "Lookup Status",
            "Error Message",
        ]

        ws.append(headers)
        ws.freeze_panes = "A2"

        for row_idx, rec in enumerate(records, start=2):
            row_data = [
                rec.get("domain") or "",
                rec.get("record_type") or "",
                rec.get("record_value") or "",
                rec.get("ttl") or "",
                rec.get("lookup_status") or "",
                rec.get("error_message") or "",
            ]
            ws.append(row_data)

            fill = self.alt_row_fill if row_idx % 2 == 1 else None
            for col_idx in range(1, len(headers) + 1):
                cell = ws.cell(row=row_idx, column=col_idx)
                cell.font = self.regular_font
                cell.border = self.thin_border
                if fill:
                    cell.fill = fill
                if col_idx in (2, 4, 5):
                    cell.alignment = self.align_center
                else:
                    cell.alignment = self.align_left

        self._style_header_row(ws, len(headers))
        self._auto_fit_columns(ws)

    def _build_sheet_ssl_details(self, wb: openpyxl.Workbook, ssl_list: List[Dict[str, Any]]):
        ws = wb.create_sheet(title="SSL Details")
        ws.views.sheetView[0].showGridLines = True

        headers = [
            "Domain",
            "Certificate Issuer",
            "Valid From",
            "Expiry Date",
            "Remaining Days",
            "Hostname Match",
            "SSL Status",
        ]

        ws.append(headers)
        ws.freeze_panes = "A2"

        for row_idx, s in enumerate(ssl_list, start=2):
            match_str = "Yes" if s.get("hostname_match") else "No"
            row_data = [
                s.get("domain") or "",
                s.get("issuer") or "",
                s.get("valid_from") or "",
                s.get("expiry_date") or "",
                s.get("remaining_days") if s.get("remaining_days") is not None else "",
                match_str,
                s.get("verification_status") or "",
            ]
            ws.append(row_data)

            fill = self.alt_row_fill if row_idx % 2 == 1 else None
            for col_idx in range(1, len(headers) + 1):
                cell = ws.cell(row=row_idx, column=col_idx)
                cell.font = self.regular_font
                cell.border = self.thin_border
                if fill:
                    cell.fill = fill
                if col_idx in (3, 4, 5, 6, 7):
                    cell.alignment = self.align_center
                else:
                    cell.alignment = self.align_left

        self._style_header_row(ws, len(headers))
        self._auto_fit_columns(ws)

    def _build_sheet_summary(self, wb: openpyxl.Workbook, scan: Dict[str, Any], results: List[Dict[str, Any]]):
        ws = wb.create_sheet(title="Summary")
        ws.views.sheetView[0].showGridLines = True

        # Header Title
        ws.cell(row=2, column=2, value="WebPulse Audit Report Summary").font = self.title_font
        ws.cell(row=3, column=2, value=f"Generated on {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}").font = self.sub_title_font

        # Calculations
        total_cnt = len(results)
        online_cnt = sum(1 for r in results if r.get("status") == "ONLINE")
        offline_cnt = sum(1 for r in results if r.get("status") == "OFFLINE")
        dns_err_cnt = sum(1 for r in results if r.get("status") == "DNS_ERROR")
        ssl_err_cnt = sum(1 for r in results if r.get("status") == "SSL_ERROR")
        http_err_cnt = sum(1 for r in results if r.get("status") == "HTTP_ERROR")
        timeout_cnt = sum(1 for r in results if r.get("status") == "TIMEOUT")

        valid_times = [
            float(r["response_time_ms"])
            for r in results
            if r.get("response_time_ms") is not None
        ]
        avg_rt = round(sum(valid_times) / len(valid_times), 1) if valid_times else 0.0

        # Section 1: KPI Metrics Table
        ws.cell(row=5, column=2, value="Metric").font = self.header_font
        ws.cell(row=5, column=2).fill = self.header_fill
        ws.cell(row=5, column=2).alignment = self.align_left

        ws.cell(row=5, column=3, value="Value").font = self.header_font
        ws.cell(row=5, column=3).fill = self.header_fill
        ws.cell(row=5, column=3).alignment = self.align_right

        metrics = [
            ("Total Websites Scanned", total_cnt),
            ("Websites Online", online_cnt),
            ("Websites Offline", offline_cnt),
            ("DNS Resolution Errors", dns_err_cnt),
            ("SSL Certificate Issues", ssl_err_cnt),
            ("HTTP Errors (4xx/5xx)", http_err_cnt),
            ("Timeouts", timeout_cnt),
            ("Average Response Time (ms)", f"{avg_rt} ms"),
            ("Overall Availability", f"{(online_cnt/total_cnt*100):.1f}%" if total_cnt else "0%"),
        ]

        curr_row = 6
        for name, val in metrics:
            c1 = ws.cell(row=curr_row, column=2, value=name)
            c2 = ws.cell(row=curr_row, column=3, value=val)
            c1.font = self.regular_font
            c1.border = self.thin_border
            c2.font = self.bold_font
            c2.border = self.thin_border
            c2.alignment = self.align_right
            if curr_row % 2 == 1:
                c1.fill = self.alt_row_fill
                c2.fill = self.alt_row_fill
            curr_row += 1

        # Section 2: Status Breakdown
        curr_row += 2
        ws.cell(row=curr_row, column=2, value="Status Classification").font = self.header_font
        ws.cell(row=curr_row, column=2).fill = self.sub_header_fill
        ws.cell(row=curr_row, column=3, value="Count").font = self.header_font
        ws.cell(row=curr_row, column=3).fill = self.sub_header_fill
        ws.cell(row=curr_row, column=3).alignment = self.align_right

        status_counts = {}
        for r in results:
            st = r.get("status", "UNKNOWN")
            status_counts[st] = status_counts.get(st, 0) + 1

        curr_row += 1
        for st_name, count in sorted(status_counts.items()):
            c1 = ws.cell(row=curr_row, column=2, value=st_name)
            c2 = ws.cell(row=curr_row, column=3, value=count)
            c1.font = self.regular_font
            c1.border = self.thin_border
            c2.font = self.bold_font
            c2.border = self.thin_border
            c2.alignment = self.align_right
            curr_row += 1

        ws.column_dimensions["B"].width = 32
        ws.column_dimensions["C"].width = 18

    def _style_header_row(self, ws: openpyxl.worksheet.worksheet.Worksheet, num_cols: int):
        ws.row_dimensions[1].height = 28
        for col_idx in range(1, num_cols + 1):
            cell = ws.cell(row=1, column=col_idx)
            cell.font = self.header_font
            cell.fill = self.header_fill
            cell.border = self.header_border
            cell.alignment = self.align_center

        # Enable auto-filter
        last_col = get_column_letter(num_cols)
        ws.auto_filter.ref = f"A1:{last_col}{max(ws.max_row, 1)}"

    def _add_conditional_formatting(self, ws: openpyxl.worksheet.worksheet.Worksheet, total_rows: int, status_col: str):
        if total_rows < 1:
            return

        end_row = total_rows + 1
        col_range = f"{status_col}2:{status_col}{end_row}"

        green_fill = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid")
        green_font = Font(color="006100", bold=True)
        red_fill = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid")
        red_font = Font(color="9C0006", bold=True)
        yellow_fill = PatternFill(start_color="FFEB9C", end_color="FFEB9C", fill_type="solid")
        yellow_font = Font(color="9C6500", bold=True)

        ws.conditional_formatting.add(col_range, CellIsRule(operator="equal", formula=['"ONLINE"'], fill=green_fill, font=green_font))
        ws.conditional_formatting.add(col_range, CellIsRule(operator="equal", formula=['"OFFLINE"'], fill=red_fill, font=red_font))
        ws.conditional_formatting.add(col_range, CellIsRule(operator="equal", formula=['"SSL_ERROR"'], fill=red_fill, font=red_font))
        ws.conditional_formatting.add(col_range, CellIsRule(operator="equal", formula=['"DNS_ERROR"'], fill=yellow_fill, font=yellow_font))
        ws.conditional_formatting.add(col_range, CellIsRule(operator="equal", formula=['"TIMEOUT"'], fill=yellow_fill, font=yellow_font))
        ws.conditional_formatting.add(col_range, CellIsRule(operator="equal", formula=['"HTTP_ERROR"'], fill=yellow_fill, font=yellow_font))

    def _auto_fit_columns(self, ws: openpyxl.worksheet.worksheet.Worksheet):
        # Fast column width calculation using sample rows (sub-millisecond)
        max_col = ws.max_column or 1
        max_row = min(ws.max_row or 1, 30)
        for col_idx in range(1, max_col + 1):
            col_letter = get_column_letter(col_idx)
            max_len = 12
            for row_idx in range(1, max_row + 1):
                val = str(ws.cell(row=row_idx, column=col_idx).value or "")
                if len(val) > max_len:
                    max_len = len(val)
            ws.column_dimensions[col_letter].width = min(max_len + 3, 45)
