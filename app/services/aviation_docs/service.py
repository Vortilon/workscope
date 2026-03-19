from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from sqlalchemy import select, update, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.aviation_document import AviationDocument, AviationDocumentTask, AviationDocumentPart
from app.services.aviation_docs.parser_excel import parse_excel_generic
from app.services.aviation_docs.parser_pdf_soma import parse_pdf_soma
from app.services.aviation_docs.utils import (
    derive_ata_chapter,
    classify_task_type,
    json_sanitize,
    new_uuid,
    normalize_document_key,
    sha256_bytes,
    utc_now_iso,
)

_TASK_REF_SUFFIX_RE = re.compile(r"^(?P<suffix>\d{3}-\d{2}-\d(?:-[A-Z0-9]+)?)$", re.IGNORECASE)
_TASK_REF_MISSING_PREFIX_RE = re.compile(r"^(?P<suffix>\d{3}-\d{2}-\d-?)$", re.IGNORECASE)


def _reconstruct_task_reference(service_interval: str | None, task_reference: str | None) -> tuple[str | None, bool]:
    """
    SOMA PDFs sometimes cause the first 3 digits of a 6-digit ATA prefix to drift into the service column.
    If service_interval ends with 3 digits and task_reference starts with the remaining 3 digits + suffix,
    we can deterministically reassemble (and must warn upstream).
    """
    if not task_reference:
        return task_reference, False
    tr = str(task_reference).strip()
    si = str(service_interval).strip() if service_interval else ""
    m = re.search(r"\b(\d{3})\b\s*$", si)
    if not m:
        return tr, False
    prefix3 = m.group(1)
    # If task ref begins with "000-.." etc, prepend prefix3
    if re.match(r"^\d{3}-\d{2}-\d", tr):
        rebuilt = f"{prefix3}{tr}"
        # Basic sanity: should now start with 6 digits
        if re.match(r"^\d{6}-\d{2}-\d", rebuilt):
            return rebuilt, True
    return tr, False


def detect_file_kind(filename: str) -> str:
    fn = (filename or "").lower()
    if fn.endswith(".pdf"):
        return "pdf"
    if fn.endswith(".xlsx") or fn.endswith(".xls") or fn.endswith(".csv"):
        return "excel"
    return "unknown"


def _try_derive_document_key(parsed_header: dict[str, Any], source_filename: str) -> str:
    # Prefer stable aircraft/work-order tuple when available; else fallback to filename base.
    reg = (parsed_header.get("registration") or "").strip()
    wo = (parsed_header.get("work_order_number") or "").strip()
    check = (parsed_header.get("check_type") or "").strip()
    if reg and wo:
        return normalize_document_key(f"{reg}::{wo}::{check}")
    base = re.sub(r"\s*\(.*\)\s*$", "", Path(source_filename).stem).strip()
    return normalize_document_key(base or source_filename)


async def ingest_document(
    db: AsyncSession,
    *,
    source_filename: str,
    stored_path: Path,
    content_bytes: bytes,
) -> AviationDocument:
    content_hash = sha256_bytes(content_bytes)
    kind = detect_file_kind(source_filename)
    parse_warnings: list[str] = []

    if kind == "pdf":
        parsed = parse_pdf_soma(stored_path)
        header = parsed.header
        sections = parsed.sections
        parts_list = parsed.parts_list
        confidence = parsed.confidence
        totals = parsed.totals
        parse_warnings.extend(parsed.parse_warnings)
    elif kind == "excel":
        parsed = parse_excel_generic(stored_path)
        header = parsed.header
        sections = parsed.sections
        parts_list = parsed.parts_list
        confidence = parsed.confidence
        totals = parsed.totals
        parse_warnings.extend(parsed.parse_warnings)
    else:
        header, sections, parts_list, totals, confidence = {"raw_fields": {}}, [], [], {}, "low"
        parse_warnings.append("Unsupported file type")

    document_key = _try_derive_document_key(header, source_filename)

    # Determine revision_index (max + 1) and flip previous latest to false.
    prev_latest = (
        await db.execute(
            select(AviationDocument).where(AviationDocument.document_key == document_key, AviationDocument.is_latest == True)  # noqa: E712
        )
    ).scalars().one_or_none()
    revision_index = (prev_latest.revision_index + 1) if prev_latest else 1
    if prev_latest:
        await db.execute(
            update(AviationDocument)
            .where(AviationDocument.id == prev_latest.id)
            .values(is_latest=False)
        )

    doc_id = new_uuid()
    parsed_at = utc_now_iso()

    canonical = {
        "document_id": doc_id,
        "source_filename": source_filename,
        "parsed_at": parsed_at,
        "confidence": confidence,
        "parse_warnings": parse_warnings,
        "header": header,
        "sections": sections,
        "parts_list": parts_list,
        "totals": totals,
    }

    doc = AviationDocument(
        id=doc_id,
        document_key=document_key,
        revision_index=revision_index,
        is_latest=True,
        source_filename=source_filename,
        stored_path=str(stored_path),
        content_sha256=content_hash,
        confidence=confidence,
        parse_warnings=parse_warnings,
        header_json=json_sanitize(header),
        totals_json=json_sanitize(totals),
        raw_json=json_sanitize(canonical),
    )
    db.add(doc)
    await db.flush()

    # Persist tasks + parts
    line_no = 0
    reconstructed_from_service = 0
    for sec in sections:
        sec_type = sec.get("section_type") or "UNKNOWN"
        for t in sec.get("tasks", []):
            line_no += 1
            service_interval = t.get("service_interval")
            task_ref_raw = t.get("task_reference")
            task_ref, did_rebuild = _reconstruct_task_reference(service_interval, task_ref_raw)
            if did_rebuild:
                reconstructed_from_service += 1
            ata, ata_derived = derive_ata_chapter(task_ref)
            task_type = t.get("task_type") or classify_task_type(task_ref, service_interval)
            db.add(
                AviationDocumentTask(
                    document_id=doc.id,
                    section_type=sec_type,
                    line_number=int(t.get("line_number") or line_no),
                    service_interval=service_interval,
                    task_reference=task_ref,
                    ata_chapter=ata,
                    ata_derived=ata_derived,
                    description=t.get("description"),
                    man_hours=t.get("man_hours"),
                    task_type=task_type,
                    ad_reference=t.get("ad_reference"),
                    component_pn=t.get("component_pn"),
                    component_sn=t.get("component_sn"),
                    component_position=t.get("component_position"),
                    component_description=t.get("component_description"),
                    status=t.get("status"),
                    raw_line=t.get("raw_line"),
                    extra_fields=json_sanitize({k: v for k, v in t.items() if k.startswith("_") or k == "extra_fields"}),
                )
            )

    for p in parts_list:
        db.add(
            AviationDocumentPart(
                document_id=doc.id,
                task_reference=p.get("task_reference"),
                part_number=p.get("part_number") or "",
                description=p.get("description"),
                part_type=p.get("part_type"),
                unit=p.get("unit"),
                quantity=p.get("quantity"),
                raw_line=p.get("raw_line"),
                extra_fields=json_sanitize(p.get("extra_fields") or {}),
            )
        )

    # Enforce totals if missing
    if not totals:
        totals = {
            "total_task_rows_in_document": line_no,
            "total_rows_extracted": line_no,
            "extraction_match": True,
            "total_mh_sum": 0.0,
            "sections_found": list({t.get("section_type") for t in sections}),
        }
        doc.totals_json = json_sanitize(totals)
        doc.raw_json["totals"] = totals

    if reconstructed_from_service:
        msg = f"Reconstructed task references by prefixing digits from service_interval: {reconstructed_from_service}"
        doc.parse_warnings = list(doc.parse_warnings or []) + [msg]
        doc.raw_json["parse_warnings"] = doc.parse_warnings

    return doc


async def list_documents(db: AsyncSession, latest_only: bool = True) -> list[dict[str, Any]]:
    q = select(AviationDocument).order_by(AviationDocument.updated_at.desc())
    if latest_only:
        q = q.where(AviationDocument.is_latest == True)  # noqa: E712
    docs = (await db.execute(q)).scalars().all()
    return [
        {
            "id": d.id,
            "document_key": d.document_key,
            "revision_index": d.revision_index,
            "is_latest": d.is_latest,
            "source_filename": d.source_filename,
            "parsed_at": d.parsed_at.isoformat() if d.parsed_at else None,
            "confidence": d.confidence,
            "parse_warnings": d.parse_warnings,
        }
        for d in docs
    ]


async def get_document_json(db: AsyncSession, document_id: str) -> dict[str, Any] | None:
    d = (await db.execute(select(AviationDocument).where(AviationDocument.id == document_id))).scalars().one_or_none()
    return d.raw_json if d else None


async def query_tasks(
    db: AsyncSession,
    *,
    document_id: str | None,
    ata_chapters: list[str] | None,
    task_references: list[str] | None,
    free_text: str | None,
    limit: int = 50,
) -> tuple[list[dict[str, Any]], int]:
    q = select(AviationDocumentTask).order_by(AviationDocumentTask.line_number).limit(min(limit, 200))
    if document_id:
        q = q.where(AviationDocumentTask.document_id == document_id)
    if ata_chapters:
        q = q.where(AviationDocumentTask.ata_chapter.in_(ata_chapters))
    if task_references:
        q = q.where(AviationDocumentTask.task_reference.in_(task_references))
    if free_text and free_text.strip():
        ft = free_text.strip()
        q = q.where(AviationDocumentTask.description.contains(ft))
    rows = (await db.execute(q)).scalars().all()
    return (
        [
            {
                "line_number": r.line_number,
                "service_interval": r.service_interval,
                "task_reference": r.task_reference,
                "ata_chapter": r.ata_chapter,
                "ata_derived": r.ata_derived,
                "description": r.description,
                "man_hours": r.man_hours,
                "task_type": r.task_type,
                "ad_reference": r.ad_reference,
                "component_pn": r.component_pn,
                "component_sn": r.component_sn,
                "component_position": r.component_position,
                "component_description": r.component_description,
                "status": r.status,
                "raw_line": r.raw_line,
                "section_type": r.section_type,
            }
            for r in rows
        ],
        len(rows),
    )

