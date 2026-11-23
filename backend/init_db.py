"""
WebPulse - Standalone Database Initialization Script
Initializes SQLite database tables and verifies schema integrity.
"""

import asyncio
import os
import sys

# Ensure backend package can be imported
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.app.config import settings
from backend.app.database.db import init_db, get_db


async def main():
    print(f"[*] Initializing WebPulse database at: {settings.db_path}")

    # Ensure directories exist
    db_dir = os.path.dirname(settings.db_path)
    if db_dir:
        os.makedirs(db_dir, exist_ok=True)
    os.makedirs(settings.screenshots_dir, exist_ok=True)
    os.makedirs(settings.reports_dir, exist_ok=True)

    await init_db()

    async with get_db() as db:
        cursor = await db.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in await cursor.fetchall()]
        print(f"[+] Successfully verified database tables: {', '.join(tables)}")

    print("[+] Database initialization complete.")


if __name__ == "__main__":
    asyncio.run(main())
