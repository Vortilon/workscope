"""
Modification / configuration evidence module (Phase 2).
Allow upload of supporting documents for PRE/POST modification or configuration status.
- Extract candidate mod/config conditions
- Map to applicability tokens
- User validates each item
- Retain evidence trail
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uuid
from pathlib import Path

from app.database import get_db
from app.config import UPLOAD_DIR
from app.models.project import Project, ModificationEvidenceFile

router = APIRouter(prefix="/api", tags=["evidence"])


@router.post("/projects/{project_id}/evidence/upload")
async def api_evidence_upload(
    project_id: int,
    db: AsyncSession = Depends(get_db),
    file: UploadFile = File(...),
):
    """Upload modification/configuration evidence file. Phase 2: extract conditions and map to applicability."""
    result = await db.execute(select(Project).where(Project.id == project_id))
    project = result.scalars().one_or_none()
    if not project:
        raise HTTPException(404)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    path = UPLOAD_DIR / f"ev_{uuid.uuid4().hex}_{file.filename or 'upload'}"
    with open(path, "wb") as f:
        f.write(await file.read())
    # Stub: extracted_conditions = await extract_conditions_from_file(path, file.content_type)
    ev = ModificationEvidenceFile(
        project_id=project_id,
        original_name=file.filename or "",
        stored_path=str(path),
        extracted_conditions=None,
        validation_status="pending",
    )
    db.add(ev)
    await db.flush()
    return {"id": ev.id, "status": "pending"}
