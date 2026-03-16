"""Web UI: Jinja + HTMX + Alpine. DAE styling with login gating."""
import json
from pathlib import Path
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.mpd import MPDDataset
from app.models.project import Project

router = APIRouter()
BASE = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE / "templates"))


def _require_login(request: Request):
    if not request.session.get("user"):
        raise HTTPException(status_code=307, detail="Redirect", headers={"Location": "/login"})


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    _require_login(request)
    return templates.TemplateResponse("home.html", {"request": request})


@router.get("/mpd", response_class=HTMLResponse)
async def mpd_library(request: Request, db: AsyncSession = Depends(get_db)):
    _require_login(request)
    result = await db.execute(select(MPDDataset).order_by(MPDDataset.manufacturer, MPDDataset.model))
    datasets = result.scalars().all()
    return templates.TemplateResponse("mpd_library.html", {"request": request, "datasets": datasets})


@router.get("/projects", response_class=HTMLResponse)
async def project_list(request: Request, db: AsyncSession = Depends(get_db)):
    _require_login(request)
    result = await db.execute(select(Project).order_by(Project.updated_at.desc()))
    projects = result.scalars().all()
    return templates.TemplateResponse("projects.html", {"request": request, "projects": projects})


@router.get("/projects/new", response_class=HTMLResponse)
async def project_new(request: Request, db: AsyncSession = Depends(get_db)):
    _require_login(request)
    result = await db.execute(select(MPDDataset).order_by(MPDDataset.manufacturer))
    datasets = result.scalars().all()
    return templates.TemplateResponse("project_new.html", {"request": request, "datasets": datasets})


@router.get("/projects/{project_id}", response_class=HTMLResponse)
async def project_detail(request: Request, project_id: int, db: AsyncSession = Depends(get_db)):
    _require_login(request)
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalars().one_or_none()
    if not project:
        raise HTTPException(404, "Project not found")
    return templates.TemplateResponse("project_detail.html", {"request": request, "project": project})


@router.get("/report/{project_id}", response_class=HTMLResponse)
async def report_page(request: Request, project_id: int, db: AsyncSession = Depends(get_db)):
    _require_login(request)
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalars().one_or_none()
    if not project:
        raise HTTPException(404, "Project not found")
    from app.services.reporting import get_report_summary
    summary = await get_report_summary(db, project_id, project.mpd_dataset_id or 0)
    summary_json = json.dumps(summary)
    return templates.TemplateResponse(
        "report.html",
        {"request": request, "project": project, "summary": summary, "summary_json": summary_json},
    )
