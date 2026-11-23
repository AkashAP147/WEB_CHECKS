# 🚀 Running WebPulse on Google Colab (with 300 Workers)

Google Colab provides a free cloud Linux environment with high-bandwidth network connectivity and multi-core CPUs, allowing WebPulse to run **300 parallel workers** smoothly.

---

## ⚡ Option 1: Quick One-Click Setup via Google Colab

1. Open [Google Colab](https://colab.research.google.com/).
2. Click **File** ➔ **Upload notebook**, and upload [`colab_run.ipynb`](file:///d:/COMMERCIAL/WEB_CHECKS/colab_run.ipynb) from this repository.
3. Click **Runtime** ➔ **Run all** (or run each cell sequentially).
4. The output will print your live **Cloudflare Tunnel URL**:
   ```
   =================================================================
   🚀 WEBPULSE IS RUNNING!
   👉 Open WebPulse: https://random-name.trycloudflare.com
   =================================================================
   ```
5. Click the URL to use WebPulse with full 300-worker scanning power!

---

## 🛠️ Option 2: Copy-Paste in an Empty Colab Notebook

If you prefer to start from an empty Colab notebook, paste these two cells:

### Cell 1 (Installation):
```bash
!git clone https://github.com/AkashAP147/WEB_CHECKS.git
%cd WEB_CHECKS

!pip install -q -r backend/requirements.txt
!pip install -q xlrd openpyxl reportlab uvicorn fastapi httpx dnspython cryptography certifi aiosqlite playwright pydantic-settings

!playwright install chromium
!playwright install-deps chromium
```

### Cell 2 (Launch WebPulse + Cloudflare Tunnel):
```python
import subprocess, time, re

# Download Cloudflare tunnel
!wget -q -nc https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -O cloudflared
!chmod +x cloudflared

# Start FastAPI + React app on port 8000
server_proc = subprocess.Popen(["python", "backend/run.py"])
time.sleep(3)

# Launch tunnel
tunnel_proc = subprocess.Popen(
    ["./cloudflared", "tunnel", "--url", "http://127.0.0.1:8000"],
    stdout=subprocess.PIPE,
    stderr=subprocess.STDOUT,
    text=True
)

for line in iter(tunnel_proc.stdout.readline, ''):
    if "trycloudflare.com" in line:
        url_match = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com", line)
        if url_match:
            print("\n🚀 Live URL:", url_match.group(0), "\n")
            break
```

---

## ⚙️ Concurrency & Worker Details:
- **300 Network Workers**: Runs up to 300 HTTP reachability checks, DNS resolutions, and SSL handshakes simultaneously.
- **20 Headless Chromium Workers**: Up to 20 full-page screenshots captured in parallel using headless Playwright.
- **Auto-Slicing**: Handles large 10,000+ URL lists by auto-slicing and processing top targets without crashing.
- **Reports**: Combined PDF & 4-Sheet Excel reports available directly from the UI.
