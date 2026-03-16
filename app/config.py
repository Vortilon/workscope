"""App configuration. SQLite for MVP; DATABASE_URL can point to Postgres later."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Base paths
BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "data" / "uploads"
MPD_STORAGE = BASE_DIR / "data" / "mpd"
REPORT_DIR = BASE_DIR / "data" / "reports"
# Ensure dirs exist at runtime
for d in (UPLOAD_DIR, MPD_STORAGE, REPORT_DIR):
    d.mkdir(parents=True, exist_ok=True)

# Database: SQLite for MVP; set DATABASE_URL for Postgres (e.g. postgresql+asyncpg://...)
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite+aiosqlite:///{BASE_DIR / 'data' / 'mpd_workscope.db'}",
)

# Sync URL for Alembic (SQLite uses 3 slashes)
SYNC_DATABASE_URL = os.getenv(
    "DATABASE_URL_SYNC",
    str(DATABASE_URL).replace("sqlite+aiosqlite://", "sqlite://").replace("postgresql+asyncpg://", "postgresql://"),
)

# AI – never send confidential data; keys only for optional bounded AI
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
GROK_API_KEY = os.getenv("GROK_API_KEY", "")
AI_PROVIDER = os.getenv("AI_PROVIDER", "grok")  # grok | openai | anthropic

# Server
PORT = int(os.getenv("PORT", "8084"))

# DAE styling
DAE_HEADER_BG = "rgb(192, 0, 0)"
DAE_HEADER_TEXT = "white"
