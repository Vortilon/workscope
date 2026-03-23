"""Web UI: Jinja + HTMX + Alpine. DAE styling with login gating."""
import json
import re as _re
from pathlib import Path
from fastapi import APIRouter, Request, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.models.mpd import MPDDataset, MPDTask
from app.models.project import Project
from app.services.normalize import normalize_applicability_tokens

router = APIRouter()
BASE = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE / "templates"))

# ── Custom Jinja2 filter: split threshold/interval into tokens ────────────────
def _interval_tokens(raw):
    if not raw:
        return []
    return [t.strip() for t in _re.split(r"[,;]", str(raw)) if t.strip()]

templates.env.filters["interval_tokens"] = _interval_tokens


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


@router.get("/mpd/{dataset_id}/tasks/{task_id}/edit", response_class=HTMLResponse)
async def mpd_task_edit_get(request: Request, dataset_id: int, task_id: int, db: AsyncSession = Depends(get_db)):
    if (r := _require_login(request)):
        return r
    t_res = await db.execute(select(MPDTask).where(MPDTask.id == task_id, MPDTask.dataset_id == dataset_id))
    task = t_res.scalars().one_or_none()
    if not task:
        raise HTTPException(404, "Task not found")
    ds_res = await db.execute(select(MPDDataset).where(MPDDataset.id == dataset_id))
    dataset = ds_res.scalars().one_or_none()
    return templates.TemplateResponse(request, "mpd_task_edit.html", {"task": task, "dataset": dataset})


@router.post("/mpd/{dataset_id}/tasks/{task_id}/edit")
async def mpd_task_edit_post(
    request: Request,
    dataset_id: int,
    task_id: int,
    mpd_item_number: str = Form(""),
    task_reference: str = Form(""),
    title: str = Form(""),
    description: str = Form(""),
    threshold_raw: str = Form(""),
    interval_raw: str = Form(""),
    applicability_raw: str = Form(""),
    section: str = Form(""),
    zone_mh: str = Form(""),
    access_mh: str = Form(""),
    preparation_mh: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    if (r := _require_login(request)):
        return r
    t_res = await db.execute(select(MPDTask).where(MPDTask.id == task_id, MPDTask.dataset_id == dataset_id))
    task = t_res.scalars().one_or_none()
    if not task:
        raise HTTPException(404, "Task not found")
    task.mpd_item_number = mpd_item_number.strip() or None
    task.task_reference   = task_reference.strip()   or None
    task.title            = title.strip()            or None
    task.description      = description.strip()      or None
    task.threshold_raw    = threshold_raw.strip()    or None
    task.interval_raw     = interval_raw.strip()     or None
    task.applicability_raw = applicability_raw.strip() or None
    task.section          = section.strip()          or None
    task.zone_mh          = zone_mh.strip()          or None
    task.access_mh        = access_mh.strip()        or None
    task.preparation_mh   = preparation_mh.strip()   or None
    tokens = normalize_applicability_tokens(applicability_raw.strip() or None)
    task.applicability_tokens_normalized = ",".join(tokens) if tokens else None
    await db.commit()
    return RedirectResponse(f"/mpd/{dataset_id}", status_code=303)


@router.post("/mpd/{dataset_id}/tasks/{task_id}/delete")
async def mpd_task_delete(request: Request, dataset_id: int, task_id: int, db: AsyncSession = Depends(get_db)):
    if (r := _require_login(request)):
        return r
    t_res = await db.execute(select(MPDTask).where(MPDTask.id == task_id, MPDTask.dataset_id == dataset_id))
    task = t_res.scalars().one_or_none()
    if task:
        await db.delete(task)
        await db.commit()
    return RedirectResponse(f"/mpd/{dataset_id}", status_code=303)


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
