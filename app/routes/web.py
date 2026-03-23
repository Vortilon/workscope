"""Web UI: Jinja + HTMX + Alpine. DAE styling with login gating."""
import json
from pathlib import Path
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.mpd import MPDDataset, MPDTask
from app.models.project import Project

router = APIRouter()
BASE = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE / "templates"))


def _redirect_login():
    return RedirectResponse("/login", status_code=303)


def _require_login(request: Request):
    """Return RedirectResponse to login if not authenticated; else None."""
    if not request.session.get("user_id"):
        return _redirect_login()
    return None


def _require_admin(request: Request):
    """Return RedirectResponse to home if not admin; else None. Use after _require_login."""
    if request.session.get("role") != "admin":
        return RedirectResponse("/", status_code=303)
    return None


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    if (r := _require_login(request)):
        return r
    return templates.TemplateResponse(request, "home.html")


@router.get("/mpd", response_class=HTMLResponse)
async def mpd_library(request: Request, db: AsyncSession = Depends(get_db)):
    if (r := _require_login(request)):
        return r
    result = await db.execute(select(MPDDataset).order_by(MPDDataset.manufacturer, MPDDataset.model, MPDDataset.revision))
    datasets = result.scalars().all()
    return templates.TemplateResponse(request, "mpd_library.html", {"datasets": datasets})


@router.get("/mpd/{dataset_id}", response_class=HTMLResponse)
async def mpd_detail(request: Request, dataset_id: int, db: AsyncSession = Depends(get_db)):
    if (r := _require_login(request)):
        return r
    ds_result = await db.execute(select(MPDDataset).where(MPDDataset.id == dataset_id))
    dataset = ds_result.scalars().one_or_none()
    if not dataset:
        raise HTTPException(404, "MPD dataset not found")
    tasks_result = await db.execute(
        select(MPDTask)
        .where(MPDTask.dataset_id == dataset_id)
        .order_by(MPDTask.row_index)
        .limit(1000)
    )
    tasks = tasks_result.scalars().all()
    return templates.TemplateResponse(request, "mpd_detail.html", {"dataset": dataset, "tasks": tasks})


@router.get("/projects", response_class=HTMLResponse)
async def project_list(request: Request, db: AsyncSession = Depends(get_db)):
    if (r := _require_login(request)):
        return r
    result = await db.execute(select(Project).order_by(Project.updated_at.desc()))
    projects = result.scalars().all()
    return templates.TemplateResponse(request, "projects.html", {"projects": projects})


@router.get("/projects/new", response_class=HTMLResponse)
async def project_new(request: Request, db: AsyncSession = Depends(get_db)):
    if (r := _require_login(request)):
        return r
    result = await db.execute(select(MPDDataset).order_by(MPDDataset.manufacturer))
    datasets = result.scalars().all()
    return templates.TemplateResponse(request, "project_new.html", {"datasets": datasets})


@router.get("/projects/{project_id}", response_class=HTMLResponse)
async def project_detail(request: Request, project_id: int, db: AsyncSession = Depends(get_db)):
    if (r := _require_login(request)):
        return r
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalars().one_or_none()
    if not project:
        raise HTTPException(404, "Project not found")
    return templates.TemplateResponse(request, "project_detail.html", {"project": project})


@router.get("/report/{project_id}", response_class=HTMLResponse)
async def report_page(request: Request, project_id: int, db: AsyncSession = Depends(get_db)):
    if (r := _require_login(request)):
        return r
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalars().one_or_none()
    if not project:
        raise HTTPException(404, "Project not found")
    from app.services.reporting import get_report_summary
    summary = await get_report_summary(db, project_id, project.mpd_dataset_id or 0)
    summary_json = json.dumps(summary)
    return templates.TemplateResponse(
        request, "report.html",
        {"project": project, "summary": summary, "summary_json": summary_json},
    )
