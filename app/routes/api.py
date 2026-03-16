"""API: MPD upload, project CRUD, workscope upload, matching, report data."""
from __future__ import annotations
import os
import uuid
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from pydantic import BaseModel

from app.database import get_db
from app.config import UPLOAD_DIR, MPD_STORAGE
from app.models.mpd import MPDDataset, MPDTask
from app.models.project import Project, ProjectFile
from app.services.mpd_import import create_dataset, import_mpd_excel, set_dataset_done
from app.services.workscope_import import parse_workscope_excel, get_candidate_mapping, detect_file_type
from app.services.matching import run_initial_matching
from app.services.reporting import get_report_summary, get_match_list

router = APIRouter(prefix="/api", tags=["api"])


class ProjectCreate(BaseModel):
    manufacturer: str
    model: str
    msn: str
    mpd_dataset_id: Optional[int] = None
    registration: Optional[str] = None


@router.get("/mpd")
async def api_list_mpd(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(MPDDataset).order_by(MPDDataset.manufacturer))
    return [{"id": d.id, "manufacturer": d.manufacturer, "model": d.model, "revision": d.revision, "parsed_status": d.parsed_status} for d in result.scalars().all()]


@router.post("/mpd/upload")
async def api_mpd_upload(
    db: AsyncSession = Depends(get_db),
    manufacturer: str = Form(...),
    model: str = Form(...),
    revision: str = Form(...),
    version: Optional[str] = Form(None),
    file: UploadFile = File(...),
):
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    ext = Path(file.filename or "").suffix.lower()
    if ext not in (".xlsx", ".xls"):
        raise HTTPException(400, "Excel file required")
    path = UPLOAD_DIR / f"mpd_{uuid.uuid4().hex}{ext}"
    with open(path, "wb") as f:
        f.write(await file.read())
    ds = await create_dataset(db, manufacturer, model, revision, version, file.filename)
    count = await import_mpd_excel(db, ds.id, path, 0, 0)
    await set_dataset_done(db, ds.id)
    return {"id": ds.id, "task_count": count}


@router.post("/projects")
async def api_create_project(body: ProjectCreate, db: AsyncSession = Depends(get_db)):
    p = Project(manufacturer=body.manufacturer, model=body.model, msn=body.msn, mpd_dataset_id=body.mpd_dataset_id, registration=body.registration)
    db.add(p)
    await db.flush()
    return {"id": p.id}


@router.get("/projects")
async def api_list_projects(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).order_by(Project.updated_at.desc()))
    return [{"id": p.id, "msn": p.msn, "manufacturer": p.manufacturer, "model": p.model, "status": p.status} for p in result.scalars().all()]


@router.get("/projects/{project_id}/report")
async def api_report(project_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalars().one_or_none()
    if not project:
        raise HTTPException(404)
    summary = await get_report_summary(db, project_id, project.mpd_dataset_id or 0)
    return summary


@router.get("/projects/{project_id}/matches")
async def api_matches(project_id: int, filter_type: Optional[str] = None, db: AsyncSession = Depends(get_db)):
    return await get_match_list(db, project_id, filter_type)


@router.post("/projects/{project_id}/workscope/upload")
async def api_workscope_upload(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    file: UploadFile = File(...),
):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalars().one_or_none()
    if not project:
        raise HTTPException(404)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    path = UPLOAD_DIR / f"ws_{uuid.uuid4().hex}_{file.filename or 'upload'}"
    with open(path, "wb") as f:
        f.write(await file.read())
    pf = ProjectFile(project_id=project_id, file_type="workscope", original_name=file.filename or "", stored_path=str(path))
    db.add(pf)
    await db.flush()
    count = await parse_workscope_excel(db, project_id, pf.id, path, 0, None)
    return {"file_id": pf.id, "rows_parsed": count}


@router.post("/projects/{project_id}/match")
async def api_run_matching(project_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalars().one_or_none()
    if not project or not project.mpd_dataset_id:
        raise HTTPException(400, "Project or MPD not set")
    counts = await run_initial_matching(db, project_id, project.mpd_dataset_id)
    return counts
