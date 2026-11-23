import os
import sys
from pathlib import Path
from pydantic_settings import BaseSettings

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    backend_host: str = "0.0.0.0"
    backend_port: int = 8000
    database_url: str = f"sqlite:///{PROJECT_ROOT / 'storage' / 'webpulse.db'}"
    screenshots_dir: str = str(PROJECT_ROOT / "storage" / "screenshots")
    reports_dir: str = str(PROJECT_ROOT / "storage" / "reports")
    max_concurrent_scans: int = 300
    max_concurrent_screenshots: int = 15
    scan_timeout: int = 15
    browser_timeout: int = 15000
    max_urls_per_scan: int = 10000
    project_root: Path = PROJECT_ROOT

    class Config:
        env_file = ".env"

    @property
    def db_path(self) -> str:
        url = self.database_url
        if url.startswith("sqlite:///"):
            return url[len("sqlite:///"):]
        return url


settings = Settings()
