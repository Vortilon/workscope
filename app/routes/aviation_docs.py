from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Header, UploadFile
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.config import UPLOAD_DIR
from app.database import get_db
from app.models.aviation_document import AviationDocument
from app.services.aviation_docs.service import ingest_document, list_documents, get_document_json, query_tasks
from app.services.aviation_docs.utils import api_key_required, safe_filename


router = APIRouter(prefix="/api/aviation", tags=["aviation-docs"])


def require_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    required = api_key_required()
    if required and (x_api_key or "").strip() != required:
        raise HTTPException(status_code=401, detail="Unauthorized")


class QueryBody(BaseModel):
    document_id: Optional[str] = None
    ata_chapters: Optional[list[str]] = None
    task_references: Optional[list[str]] = None
    free_text: Optional[str] = None
    limit: int = 50


@router.post("/upload")
async def upload_document(
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_api_key),
    file: UploadFile = File(...),
):
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Empty file")

    ext = Path(file.filename or "").suffix.lower()
    safe = safe_filename(file.filename or f"upload{ext or ''}")
    storage_dir = UPLOAD_DIR / "aviation_docs"
    storage_dir.mkdir(parents=True, exist_ok=True)
    stored_path = storage_dir / f"doc_{uuid.uuid4().hex}_{safe}"
    with open(stored_path, "wb") as f:
        f.write(raw)

    doc = await ingest_document(db, source_filename=file.filename or safe, stored_path=stored_path, content_bytes=raw)
    return {"document_id": doc.id, "document_key": doc.document_key, "revision_index": doc.revision_index, "confidence": doc.confidence, "parse_warnings": doc.parse_warnings}


@router.get("/documents")
async def get_documents(
    latest_only: bool = True,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_api_key),
):
    return await list_documents(db, latest_only=latest_only)


@router.get("/documents/{document_id}")
async def get_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_api_key),
):
    doc = await get_document_json(db, document_id)
    if not doc:
        raise HTTPException(404, "Not found")
    return doc


@router.get("/documents/{document_id}/tasks")
async def get_document_tasks(
    document_id: str,
    ata_chapter: Optional[str] = None,
    service_interval: Optional[str] = None,
    task_type: Optional[str] = None,
    limit: int = 200,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_api_key),
):
    # Use query_tasks for primary filters; apply secondary filtering in-memory to keep logic simple.
    tasks, _count = await query_tasks(
        db,
        document_id=document_id,
        ata_chapters=[ata_chapter] if ata_chapter else None,
        task_references=None,
        free_text=None,
        limit=min(limit, 200),
    )
    if service_interval:
        tasks = [t for t in tasks if (t.get("service_interval") or "").find(service_interval) >= 0]
    if task_type:
        tasks = [t for t in tasks if (t.get("task_type") or "") == task_type]
    return {"document_id": document_id, "count": len(tasks), "tasks": tasks}


@router.get("/documents/{document_id}/validate")
async def validate_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    _: None = Depends(require_api_key),
):
    d = (await db.execute(select(AviationDocument).where(AviationDocument.id == document_id))).scalars().one_or_none()
    if not d:
        raise HTTPException(404, "Not found")
    return {"document_id": d.id, "confidence": d.confidence, "parse_warnings": d.parse_warnings, "totals": d.totals_json}


@router.post("/query")
async def query(body: QueryBody, db: AsyncSession = Depends(get_db), _: None = Depends(require_api_key)):
    tasks, count = await query_tasks(
        db,
        document_id=body.document_id,
        ata_chapters=body.ata_chapters,
        task_references=body.task_references,
        free_text=body.free_text,
        limit=body.limit,
    )
    source_document = None
    aircraft = None
    check_type = None
    if body.document_id:
        d = (await db.execute(select(AviationDocument).where(AviationDocument.id == body.document_id))).scalars().one_or_none()
        if d:
            source_document = d.source_filename
            h = d.header_json or {}
            aircraft = f"{h.get('aircraft_type','')} / {h.get('registration','')} / MSN {h.get('msn','')}".strip()
            check_type = h.get("check_type")
    return {
        "source_document": source_document,
        "aircraft": aircraft,
        "check_type": check_type,
        "tasks": tasks,
        "count": count,
        "query_confidence": "high" if tasks else "medium",
    }

