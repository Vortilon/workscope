"""
Noteify MPD / Workscope Analyzer – production-ready MVP.
FastAPI + Jinja/HTMX/Alpine + SQLite (upgradeable to Postgres).
"""
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.config import BASE_DIR
from app.database import get_db
from app.routes import web, api, evidence, auth

app = FastAPI(title="Noteify MPD / Workscope Analyzer")

# Static assets (local copy of DAE logo etc.)
static_dir = BASE_DIR / "app" / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

# Simple session middleware for login state
app.add_middleware(
    SessionMiddleware,
    secret_key="noteify-mpd-session-secret",  # TODO: move to env in production
    max_age=60 * 60 * 8,
)

app.include_router(auth.router)
app.include_router(web.router)
app.include_router(api.router)
app.include_router(evidence.router)


@app.get("/health")
def health():
    return {"status": "ok", "app": "mpd-workscope"}


@app.get("/api")
def api_info():
    return {"message": "Noteify MPD – MPD vs workscope analysis", "docs": "/docs"}
