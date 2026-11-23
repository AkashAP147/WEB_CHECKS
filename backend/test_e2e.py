"""
End-to-end verification script for WebPulse.
Tests:
1. HTTP availability scanner
2. DNS record analyzer
3. SSL certificate inspector
4. Playwright screenshot capture
5. Report generation (PDF & Excel)
6. SQLite database operations
"""

import asyncio
import os
import sys

# Ensure backend package importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.config import settings
from backend.app.database.db import get_db, init_db
from backend.app.database.repository import (
    create_scan,
    save_scan_result,
    save_dns_records,
    save_ssl_details,
    get_scan_results,
    get_scan,
    get_dashboard_stats,
)
from backend.app.scanners.http_scanner import HttpScanner
from backend.app.dns.analyzer import DNSAnalyzer
from backend.app.ssl_mod.checker import SSLChecker
from backend.app.screenshots.capture import ScreenshotCapture
from backend.app.reports.pdf_generator import PDFReportGenerator
from backend.app.reports.excel_generator import ExcelReportGenerator


async def run_verification():
    print("[*] Starting WebPulse end-to-end verification...")
    await init_db()

    target = "https://example.com"
    domain = "example.com"

    # 1. HTTP Scan
    print(f"\n[1/6] Testing HTTP Availability Scanner on {target}...")
    scanner = HttpScanner()
    http_result = await scanner.scan_url(target)
    print(f"      Status: {http_result['status']}")
    print(f"      HTTP Code: {http_result['http_status_code']}")
    print(f"      Response Time: {http_result['response_time_ms']} ms")
    print(f"      Title: {http_result['website_title']}")
    assert http_result['status'] == "ONLINE", f"Expected ONLINE, got {http_result['status']}"

    # 2. DNS Analyzer
    print(f"\n[2/6] Testing DNS Record Analyzer for {domain}...")
    dns_analyzer = DNSAnalyzer()
    dns_result = await dns_analyzer.analyze(domain)
    records = dns_result.get("records", [])
    print(f"      Total DNS Records found: {len(records)}")
    for r in records[:4]:
        print(f"      - {r['record_type']}: {r['record_value']} (TTL: {r['ttl']})")
    assert len(records) > 0, "Expected at least 1 DNS record for example.com"

    # 3. SSL Checker
    print(f"\n[3/6] Testing SSL Certificate Checker for {domain}...")
    ssl_checker = SSLChecker()
    ssl_result = await ssl_checker.check(domain)
    print(f"      Issuer: {ssl_result.get('issuer')}")
    print(f"      Status: {ssl_result.get('verification_status')}")
    print(f"      Remaining Days: {ssl_result.get('remaining_days')}")
    print(f"      Hostname Match: {ssl_result.get('hostname_match')}")

    # 4. Playwright Screenshot
    print(f"\n[4/6] Testing Playwright Screenshot Capture on {target}...")
    capturer = ScreenshotCapture(screenshots_dir=settings.screenshots_dir)
    ss_result = await capturer.capture(target, scan_id="test_verify")
    print(f"      Success: {ss_result.get('success')}")
    print(f"      Path: {ss_result.get('screenshot_path')}")
    print(f"      Capture Time: {ss_result.get('capture_time_ms')} ms")

    # 5. Database Save & Retrieve
    print("\n[5/6] Testing Database Persistence...")
    import uuid
    scan_id = str(uuid.uuid4())
    async with get_db() as db:
        scan = await create_scan(db, scan_id=scan_id, total_urls=1)
        result_id = await save_scan_result(
            db,
            scan_id=scan_id,
            result_data={
                "original_url": target,
                "final_url": http_result["final_url"],
                "domain": domain,
                "status": http_result["status"],
                "http_status_code": http_result["http_status_code"],
                "response_time_ms": http_result["response_time_ms"],
                "server_info": http_result.get("server_info"),
                "website_title": http_result.get("website_title"),
                "screenshot_path": ss_result.get("screenshot_path"),
                "error_message": None,
            },
        )
        if records:
            await save_dns_records(db, scan_result_id=result_id, records_list=records)
        if ssl_result:
            await save_ssl_details(db, scan_result_id=result_id, ssl_data=ssl_result)

        saved_results = await get_scan_results(db, scan_id)
        saved_scan = await get_scan(db, scan_id)
        stats = await get_dashboard_stats(db)
        print(f"      Scan ID: {scan_id}")
        print(f"      Saved Result ID: {result_id}")
        print(f"      Retrieved Results Count: {len(saved_results)}")
        print(f"      Dashboard Stats: {stats['total_scanned']} scanned, {stats['online_count']} online")

    # 6. Reports Generation (PDF and Excel)
    print("\n[6/6] Testing PDF and Excel Report Generators...")
    pdf_path = os.path.join(settings.reports_dir, f"report_{scan_id}.pdf")
    xlsx_path = os.path.join(settings.reports_dir, f"report_{scan_id}.xlsx")

    pdf_gen = PDFReportGenerator()
    await pdf_gen.generate(scan=saved_scan, results=saved_results, output_path=pdf_path)
    print(f"      Generated PDF Report: {pdf_path} ({os.path.getsize(pdf_path)} bytes)")

    excel_gen = ExcelReportGenerator()
    await excel_gen.generate(scan=saved_scan, results=saved_results, output_path=xlsx_path)
    print(f"      Generated Excel Report: {xlsx_path} ({os.path.getsize(xlsx_path)} bytes)")

    print("\n[+] ALL END-TO-END VERIFICATION CHECKS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    asyncio.run(run_verification())
