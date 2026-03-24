"""API: MPD upload, project CRUD, workscope upload, matching, report data."""
from __future__ import annotations
import os
import uuid
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
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
    aircraft_type_id: Optional[int] = None
    engine_type_id: Optional[int] = None
    mpd_dataset_id: Optional[int] = None
    operator_id: Optional[int] = None
    registration: Optional[str] = None


@router.get("/mpd")
async def api_list_mpd(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(MPDDataset).order_by(MPDDataset.manufacturer))
    return [{"id": d.id, "manufacturer": d.manufacturer, "model": d.model, "revision": d.revision, "parsed_status": d.parsed_status} for d in result.scalars().all()]


@router.get("/mpd/datasets")
async def api_list_mpd_datasets(db: AsyncSession = Depends(get_db)):
    """Read-only: list all MPD datasets (same as GET /api/mpd)."""
    result = await db.execute(select(MPDDataset).order_by(MPDDataset.manufacturer, MPDDataset.model, MPDDataset.revision))
    return [
        {
            "id": d.id,
            "manufacturer": d.manufacturer,
            "model": d.model,
            "revision": d.revision,
            "parsed_status": d.parsed_status,
            "source_file": d.source_file,
            "created_at": d.created_at.isoformat() if d.created_at else None,
        }
        for d in result.scalars().all()
    ]


@router.get("/mpd/datasets/{dataset_id}/tasks")
async def api_list_mpd_tasks(
    dataset_id: int,
    db: AsyncSession = Depends(get_db),
    section: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
):
    """Read-only: list MPD tasks for a dataset. Optional filter by ATA section (e.g. section=32)."""
    ds = (await db.execute(select(MPDDataset).where(MPDDataset.id == dataset_id))).scalars().one_or_none()
    if not ds:
        raise HTTPException(404, "MPD dataset not found")
    q = select(MPDTask).where(MPDTask.dataset_id == dataset_id).order_by(MPDTask.row_index)
    if section is not None and section != "":
        q = q.where(
            or_(
                MPDTask.section.contains(section),
                MPDTask.chapter.contains(section),
            )
        )
    q = q.offset(offset).limit(min(limit, 1000))
    result = await db.execute(q)
    tasks = result.scalars().all()
    return [
        {
            "id": t.id,
            "dataset_id": t.dataset_id,
            "mpd_item_number": t.mpd_item_number,
            "task_reference": t.task_reference,
            "task_number": t.task_number,
            "task_code": t.task_code,
            "title": t.title,
            "description": t.description,
            "section": t.section,
            "chapter": t.chapter,
            "threshold_raw": t.threshold_raw,
            "interval_raw": t.interval_raw,
            "threshold_normalized": t.threshold_normalized,
            "interval_normalized": t.interval_normalized,
            "interval_json": t.interval_json,
            "source_references": t.source_references,
            "applicability_raw": t.applicability_raw,
            "applicability_tokens_normalized": t.applicability_tokens_normalized,
            "job_procedure": t.job_procedure,
            "mp_reference": t.mp_reference,
            "cmm_reference": t.cmm_reference,
            "zones": t.zones,
            "zone_mh": t.zone_mh,
            "man": t.man,
            "access_items": t.access_items,
            "access_mh": t.access_mh,
            "preparation_description": t.preparation_description,
            "preparation_mh": t.preparation_mh,
            "skill": t.skill,
            "equipment": t.equipment,
            "extra_raw": t.extra_raw,
            "row_index": t.row_index,
        }
        for t in tasks
    ]


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
    p = Project(
        manufacturer=body.manufacturer,
        model=body.model,
        aircraft_type_id=body.aircraft_type_id,
        engine_type_id=body.engine_type_id,
        msn=body.msn,
        mpd_dataset_id=body.mpd_dataset_id,
        operator_id=body.operator_id,
        registration=body.registration,
    )
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
