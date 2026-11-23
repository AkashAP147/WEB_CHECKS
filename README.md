# WebPulse — Website Health & DNS Audit Platform

WebPulse is an enterprise-grade website health, DNS configuration, SSL certificate, and visual appearance audit platform. Built with **FastAPI**, **React (Vite + TypeScript)**, **HTTPX**, **dnspython**, **Playwright**, **OpenPyXL**, and **ReportLab**.

---

## 🌟 Key Features

- **Multi-Vector Website Scanning**:
  - HTTP reachability, status code capture, redirect chain tracking, and latency benchmarks.
  - Comprehensive status classification: `ONLINE`, `OFFLINE`, `HTTP_ERROR`, `TIMEOUT`, `SSL_ERROR`, `DNS_ERROR`, `BROWSER_ERROR`, `BLOCKED`.
  - Nuanced error discrimination: 403, 404, or 500 responses are preserved as HTTP responses with diagnostic details rather than simply labeled as offline.
- **Deep DNS Record Analyzer**:
  - Full record extraction: `A`, `AAAA`, `CNAME`, `MX`, `NS`, `TXT`, `SOA`, `CAA`.
  - Detection of SPF and DMARC TXT policies, IPv4/IPv6 resolution, name servers, and mail exchanges.
  - Interactive record type filtering.
- **SSL / TLS Certificate Inspector**:
  - Subject, Issuer, Valid From / Expiry dates, and remaining validity days.
  - Hostname verification matching and warnings for expiring or untrusted certificates.
- **Automated Visual Capture (Playwright)**:
  - Headless Chromium desktop rendering (1440 × 900) of scanned targets.
  - Interactive visual gallery with full-size lightbox preview and direct image download.
- **Professional Reporting**:
  - **PDF Audit Report**: Cover page, executive summary KPI metrics, status distribution, and individual target audit sheets with screenshots generated via ReportLab.
  - **Excel Audit Report**: Multi-tab formatted workbook (`Website Status`, `DNS Records`, `SSL Details`, `Summary`) with auto-filters, frozen headers, and conditional formatting via OpenPyXL.
- **Multiple Input Modes**:
  - Single URL scanner with instant lookup.
  - Bulk multi-line URL textarea input.
  - Excel file upload (`.xlsx`, `.xls`) with automated column parsing.
- **Security & SSRF Hardening**:
  - Protection against Server-Side Request Forgery (SSRF).
  - Blocks private IP ranges (RFC 1918), loopback (`127.0.0.0/8`, `::1`), and cloud metadata services (`169.254.169.254`, `metadata.google.internal`).
  - Target re-validation across redirect hops.

---

## 🛠️ Technology Stack

| Layer | Technologies |
|---|---|
| **Frontend** | React 19, Vite, TypeScript, Tailwind CSS, Lucide React, Recharts |
| **Backend** | Python 3.10+, FastAPI, Uvicorn, HTTPX, aiosqlite, Pydantic v2 |
| **DNS Engine** | dnspython |
| **Browser Automation**| Playwright (Chromium) |
| **Report Engine** | ReportLab (PDF), OpenPyXL (Excel) |
| **Database** | SQLite with asynchronous WAL mode |

---

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.10 or higher
- Node.js 18 or higher & npm
- Git

### 2. Environment Configuration
Copy the sample environment file:
```bash
cp .env.example .env
```

### 3. Backend Setup

1. Open a terminal in the project root:
```bash
cd backend
```

2. Install Python dependencies:
```bash
pip install -r requirements.txt
```

3. Install Playwright browser binaries:
```bash
playwright install chromium
```

4. Initialize the SQLite database:
```bash
python init_db.py
```

5. Start the FastAPI backend server:
```bash
python run.py
```
The API documentation is accessible at: `http://localhost:8000/docs`

---

### 4. Frontend Setup

1. In a separate terminal, navigate to the frontend directory:
```bash
cd frontend
```

2. Install npm dependencies:
```bash
npm install
```

3. Start the Vite development server:
```bash
npm run dev
```
Open your browser at: `http://localhost:5173`

---

## 📁 Project Architecture

```
d:/COMMERCIAL/WEB_CHECKS/
├── backend/
│   ├── app/
│   │   ├── api/routes.py          # FastAPI endpoints (scans, history, reports, ws)
│   │   ├── config.py              # Environment settings & directories
│   │   ├── database/              # SQLite setup & async repository
│   │   │   ├── db.py
│   │   │   └── repository.py
│   │   ├── dns/analyzer.py        # dnspython asynchronous DNS resolver
│   │   ├── reports/               # PDF & Excel report engines
│   │   │   ├── pdf_generator.py
│   │   │   └── excel_generator.py
│   │   ├── scanners/http_scanner.py # HTTPX availability & redirect engine
│   │   ├── schemas/scan.py        # Pydantic models for validation
│   │   ├── screenshots/capture.py # Playwright Chromium full-page renderer
│   │   ├── services/scan_service.py # Core scan orchestrator & queue
│   │   ├── ssl_mod/checker.py     # SSL certificate inspection
│   │   ├── utils/url_validator.py # SSRF protection & Excel parsing
│   │   └── main.py                # FastAPI lifecycle & static mounting
│   ├── init_db.py                 # Database creation script
│   ├── requirements.txt
│   └── run.py
├── frontend/
│   ├── src/
│   │   ├── hooks/                 # useScan, useTheme
│   │   ├── layouts/MainLayout.tsx # Collapsible sidebar & responsive header
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx      # Metrics, Recharts pie charts & recent table
│   │   │   ├── Scanner.tsx        # Single/Bulk/Excel scanner with live progress
│   │   │   ├── ScanResults.tsx    # Detailed diagnostic inspection per target
│   │   │   ├── History.tsx        # Searchable scan history & report downloads
│   │   │   └── Screenshots.tsx    # Visual screenshot gallery & lightbox
│   │   ├── services/api.ts        # Axios API client
│   │   ├── types/index.ts         # TypeScript definitions
│   │   ├── utils/helpers.ts       # Formatting, badges & downloads
│   │   ├── App.tsx
│   │   ├── main.tsx
│   │   └── index.css              # Tailwind styles & theme variables
│   ├── package.json
│   ├── tailwind.config.js
│   └── vite.config.ts
└── storage/
    ├── screenshots/               # Stored PNG visual captures
    └── reports/                   # Stored PDF & XLSX reports
```

---

## 🔒 Security Hardening

- **SSRF Protection**: Target URLs are validated before outbound socket requests. IP addresses resolving to loopback (`127.0.0.1`), private RFC 1918 subnets (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), link-local (`169.254.0.0/16`), and internal metadata addresses are blocked.
- **Redirect Re-validation**: In multi-hop redirects, every intermediate and terminal location header is re-checked against SSRF blacklist rules before following.
- **Resource Limits**: Concurrency limits (default 5 concurrent tasks) and request timeouts prevent thread starvation.
