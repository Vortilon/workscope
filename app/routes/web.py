"""Web UI: Jinja + HTMX + Alpine. DAE styling with login gating."""
import json
import re as _re
import shutil
from pathlib import Path
from fastapi import APIRouter, Request, Depends, HTTPException, Form
from fastapi.responses import HTMLResponse, RedirectResponse, FileResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.config import MPD_STORAGE
from app.database import get_db
from app.models.mpd import MPDDataset, MPDTask
from app.models.project import Project
from app.services.normalize import (
    normalize_applicability_tokens,
    threshold_tokens as _thr_tokens_fn,
    interval_tokens as _int_tokens_fn,
)

router = APIRouter()
BASE = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE / "templates"))

# ── Custom Jinja2 filters ────────────────────────────────────────────────────
templates.env.filters["threshold_tokens"] = _thr_tokens_fn
templates.env.filters["interval_tokens"]  = _int_tokens_fn


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
async def mpd_library(request: Request, error: str = "", db: AsyncSession = Depends(get_db)):
    if (r := _require_login(request)):
        return r
    result = await db.execute(
        select(MPDDataset).order_by(MPDDataset.manufacturer, MPDDataset.model, MPDDataset.revision)
    )
    datasets = result.scalars().all()

    # Task counts per dataset (single query)
    counts_res = await db.execute(
        select(MPDTask.dataset_id, func.count().label("cnt")).group_by(MPDTask.dataset_id)
    )
    task_counts = {row.dataset_id: row.cnt for row in counts_res}

    # Which dataset IDs are referenced by at least one project
    used_res = await db.execute(
        select(Project.mpd_dataset_id).where(Project.mpd_dataset_id.is_not(None)).distinct()
    )
    in_use_ids = {row.mpd_dataset_id for row in used_res}

    # Which dataset IDs have a stored source file
    has_file_ids = set()
    for ds in datasets:
        for ext in (".xlsx", ".xls"):
            if (MPD_STORAGE / f"mpd_{ds.id}{ext}").exists():
                has_file_ids.add(ds.id)
                break

    return templates.TemplateResponse(request, "mpd_library.html", {
        "datasets": datasets,
        "task_counts": task_counts,
        "in_use_ids": in_use_ids,
        "has_file_ids": has_file_ids,
        "error": error,
    })


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


@router.get("/mpd/{dataset_id}/download")
async def mpd_dataset_download(request: Request, dataset_id: int, db: AsyncSession = Depends(get_db)):
    if (r := _require_login(request)):
        return r
    for ext in (".xlsx", ".xls"):
        fp = MPD_STORAGE / f"mpd_{dataset_id}{ext}"
        if fp.exists():
            ds = (await db.execute(select(MPDDataset).where(MPDDataset.id == dataset_id))).scalars().one_or_none()
            filename = (ds.source_file if ds and ds.source_file else f"mpd_{dataset_id}{ext}")
            return FileResponse(
                str(fp), filename=filename,
                media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
    raise HTTPException(404, "Source file not available")


@router.post("/mpd/{dataset_id}/delete")
async def mpd_dataset_delete(request: Request, dataset_id: int, db: AsyncSession = Depends(get_db)):
    if (r := _require_login(request)):
        return r
    if request.session.get("role") != "admin":
        raise HTTPException(403, "Admin only")

    # Block deletion if any project references this dataset
    in_use = (await db.execute(
        select(func.count()).select_from(Project).where(Project.mpd_dataset_id == dataset_id)
    )).scalar() or 0
    if in_use:
        return RedirectResponse(f"/mpd?error=in_use_{dataset_id}", status_code=303)

    ds = (await db.execute(select(MPDDataset).where(MPDDataset.id == dataset_id))).scalars().one_or_none()
    if ds:
        # Remove stored source file
        for ext in (".xlsx", ".xls"):
            fp = MPD_STORAGE / f"mpd_{dataset_id}{ext}"
            fp.unlink(missing_ok=True)
        await db.delete(ds)
        await db.commit()
    return RedirectResponse("/mpd", status_code=303)


@router.post("/mpd/{dataset_id}/toggle-superseded")
async def mpd_dataset_toggle_superseded(request: Request, dataset_id: int, db: AsyncSession = Depends(get_db)):
    if (r := _require_login(request)):
        return r
    if request.session.get("role") != "admin":
        raise HTTPException(403, "Admin only")
    ds = (await db.execute(select(MPDDataset).where(MPDDataset.id == dataset_id))).scalars().one_or_none()
    if not ds:
        raise HTTPException(404, "Dataset not found")
    ds.is_superseded = not ds.is_superseded
    await db.commit()
    return RedirectResponse("/mpd", status_code=303)


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
