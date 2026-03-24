"""Workscope import wizard for projects — Excel and PDF (table extraction).
Flow:  /projects/{id}/workscope/upload  →  mapping  →  run  →  result
"""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import IMPORT_TEMP_DIR
from app.database import get_db
from app.models.project import Project
from app.models.workscope import WorkscopeImportRow
from app.routes.web import _require_login

router = APIRouter()
BASE = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE / "templates"))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _col_letter(idx: int) -> str:
    """0-based column index → Excel letter (A, B, …, Z, AA, …)."""
    result = ""
    n = idx + 1
    while n:
        n, r = divmod(n - 1, 26)
        result = chr(65 + r) + result
    return result


def _read_workbook(path: Path) -> dict:
    """Read .xlsx or .xls into {sheet_name: [[cell,...], ...]} (list of rows)."""
    ext = path.suffix.lower()
    if ext == ".xls":
        import xlrd
        wb = xlrd.open_workbook(str(path))
        out = {}
        for name in wb.sheet_names():
            sh = wb.sheet_by_name(name)
            out[name] = [
                [str(sh.cell_value(r, c)).strip() for c in range(sh.ncols)]
                for r in range(sh.nrows)
            ]
        return out
    else:
        import openpyxl
        wb = openpyxl.load_workbook(str(path), data_only=True, read_only=True)
        out = {}
        for name in wb.sheetnames:
            sh = wb[name]
            out[name] = [
                [str(cell.value or "").strip() for cell in row]
                for row in sh
            ]
        return out


def _detect_header_row(rows: list[list[str]]) -> int:
    """Heuristic: first row with ≥ 3 non-empty cells that looks like headers."""
    for i, row in enumerate(rows[:15]):
        non_empty = sum(1 for c in row if c)
        if non_empty >= 3:
            return i
    return 0


WORKSCOPE_FIELD_KEYS = ["task_ref", "mpd_ref", "description", "zone", "section", "mh", "cost"]
WORKSCOPE_FIELD_LABELS = {
    "task_ref": "Task Reference (workscope)",
    "mpd_ref": "MPD Task Reference (for crosscheck)",
    "description": "Description",
    "zone": "Zone",
    "section": "Section / ATA",
    "mh": "Man-Hours",
    "cost": "Cost / Price",
}


def _guess_mapping(headers: list[str]) -> dict[str, int | None]:
    """Auto-suggest column mapping based on header text heuristics."""
    patterns = {
        "task_ref": re.compile(r"task\s*(?:ref|no|num|number)?|work\s*order|line", re.I),
        "mpd_ref": re.compile(r"mpd|mpdref|ref\s*mpd|maint.*ref|task.*ref|ata.*ref", re.I),
        "description": re.compile(r"desc|title|work|activity", re.I),
        "zone": re.compile(r"zone|area", re.I),
        "section": re.compile(r"section|ata|chapter", re.I),
        "mh": re.compile(r"man.*hour|mh|hours?|labour|labor", re.I),
        "cost": re.compile(r"cost|price|amount|value|total", re.I),
    }
    mapping: dict[str, int | None] = {k: None for k in WORKSCOPE_FIELD_KEYS}
    for ci, h in enumerate(headers):
        for field, pat in patterns.items():
            if mapping[field] is None and pat.search(h):
                mapping[field] = ci
    return mapping


# ── Upload step ───────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/workscope/upload", response_class=HTMLResponse)
async def ws_upload_get(request: Request, project_id: int, db: AsyncSession = Depends(get_db)):
    if (r := _require_login(request)):
        return r
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalars().one_or_none()
    if not project:
        raise HTTPException(404, "Project not found")
    return templates.TemplateResponse(request, "workscope_import/upload.html", {"project": project})


@router.post("/projects/{project_id}/workscope/upload", response_class=HTMLResponse)
async def ws_upload_post(
    request: Request,
    project_id: int,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    if (r := _require_login(request)):
        return r
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalars().one_or_none()
    if not project:
        raise HTTPException(404, "Project not found")

    ext = Path(file.filename).suffix.lower()
    if ext not in (".xlsx", ".xls", ".pdf"):
        return templates.TemplateResponse(
            request, "workscope_import/upload.html",
            {"project": project, "error": "Only .xlsx, .xls, or .pdf files are accepted."},
        )

    IMPORT_TEMP_DIR.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    path = IMPORT_TEMP_DIR / f"ws_{token}{ext}"
    path.write_bytes(await file.read())

    if ext == ".pdf":
        # PDF path → redirect to PDF mapping (simplified: extract text tables)
        request.session["ws_import"] = {
            "project_id": project_id,
            "token": token,
            "ext": ext,
            "filename": file.filename,
            "source": "pdf",
        }
        return RedirectResponse(f"/projects/{project_id}/workscope/pdf-mapping", status_code=303)

    # Excel path: read sheets and go to sheet selector / mapping
    try:
        sheets_data = _read_workbook(path)
    except Exception as exc:
        path.unlink(missing_ok=True)
        return templates.TemplateResponse(
            request, "workscope_import/upload.html",
            {"project": project, "error": f"Could not read file: {exc}"},
        )

    sheets_summary = {}
    for sname, rows in sheets_data.items():
        non_empty = sum(1 for r in rows if any(c for c in r))
        sheets_summary[sname] = non_empty

    request.session["ws_import"] = {
        "project_id": project_id,
        "token": token,
        "ext": ext,
        "filename": file.filename,
        "source": "excel",
        "sheets": list(sheets_data.keys()),
        "sheets_summary": sheets_summary,
    }
    return RedirectResponse(f"/projects/{project_id}/workscope/mapping", status_code=303)


# ── Excel mapping step ────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/workscope/mapping", response_class=HTMLResponse)
async def ws_mapping_get(
    request: Request,
    project_id: int,
    sheet: str = "",
    header_row: int = -1,
    db: AsyncSession = Depends(get_db),
):
    if (r := _require_login(request)):
        return r
    sess = request.session.get("ws_import", {})
    if sess.get("project_id") != project_id or sess.get("source") != "excel":
        return RedirectResponse(f"/projects/{project_id}/workscope/upload")

    project = (await db.execute(select(Project).where(Project.id == project_id))).scalars().one_or_none()
    if not project:
        raise HTTPException(404)

    token = sess["token"]
    ext = sess["ext"]
    path = IMPORT_TEMP_DIR / f"ws_{token}{ext}"
    sheets_data = _read_workbook(path)

    sheets = list(sheets_data.keys())
    active_sheet = sheet if sheet in sheets_data else sheets[0]
    rows = sheets_data[active_sheet]

    if header_row < 0:
        header_row = _detect_header_row(rows)

    header = rows[header_row] if header_row < len(rows) else []
    # Build column info with letter + caption + sample value
    sample_row_idx = header_row + 5 if header_row + 5 < len(rows) else (header_row + 1 if header_row + 1 < len(rows) else -1)
    sample_row = rows[sample_row_idx] if sample_row_idx >= 0 else []

    col_infos = []
    for ci, h in enumerate(header):
        sample = sample_row[ci] if ci < len(sample_row) else ""
        fill_rate = sum(1 for r in rows[header_row + 1:] if ci < len(r) and r[ci]) / max(1, len(rows) - header_row - 1)
        col_infos.append({
            "idx": ci,
            "letter": _col_letter(ci),
            "caption": h,
            "label": f"{_col_letter(ci)} – {h}" if h else f"{_col_letter(ci)} (blank)",
            "sample": sample,
            "fill_pct": round(fill_rate * 100),
        })

    total_data_rows = max(0, len(rows) - header_row - 1)
    guessed = _guess_mapping(header)

    # Scan interval/threshold/mh columns for unknown or ambiguous units
    from app.services.normalize import scan_column_for_unknown_units
    unit_warnings: list[dict] = []
    interval_kws = {"interval", "threshold", "limit", "mh", "man", "hour", "fh", "fc"}
    for ci, info in enumerate(col_infos):
        if not any(kw in info["caption"].lower() for kw in interval_kws):
            continue
        col_vals = [
            rows[r][ci] for r in range(header_row + 1, len(rows))
            if ci < len(rows[r]) and rows[r][ci]
        ][:100]  # scan first 100 data rows
        for w in scan_column_for_unknown_units(col_vals):
            w["col_letter"] = info["letter"]
            w["col_caption"] = info["caption"]
            if not any(x["unit"] == w["unit"] for x in unit_warnings):
                unit_warnings.append(w)

    return templates.TemplateResponse(request, "workscope_import/mapping.html", {
        "project": project,
        "sheets": sheets,
        "sheets_summary": sess.get("sheets_summary", {}),
        "active_sheet": active_sheet,
        "header_row": header_row,
        "col_infos": col_infos,
        "field_keys": WORKSCOPE_FIELD_KEYS,
        "field_labels": WORKSCOPE_FIELD_LABELS,
        "guessed": guessed,
        "total_data_rows": total_data_rows,
        "filename": sess.get("filename", ""),
        "unit_warnings": unit_warnings,
    })


# ── Excel run step ────────────────────────────────────────────────────────────

@router.post("/projects/{project_id}/workscope/run", response_class=HTMLResponse)
async def ws_run(
    request: Request,
    project_id: int,
    sheet: str = Form(...),
    header_row: int = Form(...),
    col_task_ref: str = Form(""),
    col_mpd_ref: str = Form(""),
    col_description: str = Form(""),
    col_zone: str = Form(""),
    col_section: str = Form(""),
    col_mh: str = Form(""),
    col_cost: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    if (r := _require_login(request)):
        return r
    sess = request.session.get("ws_import", {})
    if sess.get("project_id") != project_id:
        return RedirectResponse(f"/projects/{project_id}/workscope/upload")

    project = (await db.execute(select(Project).where(Project.id == project_id))).scalars().one_or_none()
    if not project:
        raise HTTPException(404)

    token = sess["token"]
    ext = sess["ext"]
    path = IMPORT_TEMP_DIR / f"ws_{token}{ext}"
    sheets_data = _read_workbook(path)
    rows = sheets_data.get(sheet, [])

    def _col(s: str) -> int | None:
        try:
            v = int(s)
            return v if v >= 0 else None
        except (ValueError, TypeError):
            return None

    col_map = {
        "task_ref": _col(col_task_ref),
        "mpd_ref": _col(col_mpd_ref),
        "description": _col(col_description),
        "zone": _col(col_zone),
        "section": _col(col_section),
        "mh": _col(col_mh),
        "cost": _col(col_cost),
    }

    def _get(row: list[str], ci: int | None) -> str:
        if ci is None or ci >= len(row):
            return ""
        return row[ci].strip()

    # Delete previous import rows for this project (fresh import)
    existing = (await db.execute(
        select(WorkscopeImportRow).where(WorkscopeImportRow.project_id == project_id)
    )).scalars().all()
    for r_old in existing:
        await db.delete(r_old)
    await db.flush()

    header = rows[header_row] if header_row < len(rows) else []
    mapped_cols = set(v for v in col_map.values() if v is not None)

    count = 0
    errors = []
    for idx in range(header_row + 1, len(rows)):
        row = rows[idx]
        task_ref = _get(row, col_map["task_ref"])
        mpd_ref = _get(row, col_map["mpd_ref"])
        desc = _get(row, col_map["description"])
        if not task_ref and not mpd_ref and not desc:
            continue
        count += 1
        # Preserve all other columns in extra_raw
        extra: dict[str, str] = {}
        for ci, cell in enumerate(row):
            if ci not in mapped_cols and cell:
                lbl = header[ci] if ci < len(header) else f"col_{ci}"
                extra[lbl or f"col_{ci}"] = cell

        ws_row = WorkscopeImportRow(
            project_id=project_id,
            seq=count,
            source="excel",
            task_ref=task_ref or None,
            mpd_ref=mpd_ref or None,
            description=desc or None,
            zone=_get(row, col_map["zone"]) or None,
            section=_get(row, col_map["section"]) or None,
            mh=_get(row, col_map["mh"]) or None,
            cost=_get(row, col_map["cost"]) or None,
            extra_raw=extra or None,
        )
        db.add(ws_row)

    await db.commit()
    path.unlink(missing_ok=True)
    request.session.pop("ws_import", None)

    return templates.TemplateResponse(request, "workscope_import/result.html", {
        "project": project,
        "imported": count,
        "errors": errors,
        "source": "excel",
    })


# ── PDF step (simplified) ─────────────────────────────────────────────────────

@router.get("/projects/{project_id}/workscope/pdf-mapping", response_class=HTMLResponse)
async def ws_pdf_mapping_get(request: Request, project_id: int, db: AsyncSession = Depends(get_db)):
    if (r := _require_login(request)):
        return r
    sess = request.session.get("ws_import", {})
    if sess.get("project_id") != project_id or sess.get("source") != "pdf":
        return RedirectResponse(f"/projects/{project_id}/workscope/upload")
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalars().one_or_none()
    if not project:
        raise HTTPException(404)

    token = sess["token"]
    path = IMPORT_TEMP_DIR / f"ws_{token}.pdf"

    # Extract tables from PDF using pdfplumber
    tables: list[list[list[str]]] = []
    try:
        import pdfplumber
        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages[:5]:  # preview first 5 pages
                tbl = page.extract_table()
                if tbl:
                    tables.append([[str(c or "").strip() for c in r] for r in tbl[:6]])
    except Exception as exc:
        tables = []

    preview_rows = tables[0] if tables else []
    header_row = 0
    header = preview_rows[header_row] if preview_rows else []
    col_infos = [
        {"idx": ci, "letter": _col_letter(ci), "caption": h, "label": f"{_col_letter(ci)} – {h}" if h else f"{_col_letter(ci)}"}
        for ci, h in enumerate(header)
    ]
    guessed = _guess_mapping(header)

    return templates.TemplateResponse(request, "workscope_import/pdf_mapping.html", {
        "project": project,
        "col_infos": col_infos,
        "field_keys": WORKSCOPE_FIELD_KEYS,
        "field_labels": WORKSCOPE_FIELD_LABELS,
        "guessed": guessed,
        "preview": preview_rows[:6],
        "filename": sess.get("filename", ""),
    })


@router.post("/projects/{project_id}/workscope/pdf-run", response_class=HTMLResponse)
async def ws_pdf_run(
    request: Request,
    project_id: int,
    col_task_ref: str = Form(""),
    col_mpd_ref: str = Form(""),
    col_description: str = Form(""),
    col_zone: str = Form(""),
    col_section: str = Form(""),
    col_mh: str = Form(""),
    col_cost: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    if (r := _require_login(request)):
        return r
    sess = request.session.get("ws_import", {})
    if sess.get("project_id") != project_id:
        return RedirectResponse(f"/projects/{project_id}/workscope/upload")

    project = (await db.execute(select(Project).where(Project.id == project_id))).scalars().one_or_none()
    if not project:
        raise HTTPException(404)

    token = sess["token"]
    path = IMPORT_TEMP_DIR / f"ws_{token}.pdf"

    def _col(s: str) -> int | None:
        try:
            v = int(s)
            return v if v >= 0 else None
        except (ValueError, TypeError):
            return None

    col_map = {
        "task_ref": _col(col_task_ref),
        "mpd_ref": _col(col_mpd_ref),
        "description": _col(col_description),
        "zone": _col(col_zone),
        "section": _col(col_section),
        "mh": _col(col_mh),
        "cost": _col(col_cost),
    }

    import pdfplumber
    rows_all: list[list[str]] = []
    try:
        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages:
                tbl = page.extract_table()
                if tbl:
                    for row in tbl:
                        rows_all.append([str(c or "").strip() for c in row])
    except Exception:
        pass

    # Delete previous
    for r_old in (await db.execute(select(WorkscopeImportRow).where(WorkscopeImportRow.project_id == project_id))).scalars().all():
        await db.delete(r_old)
    await db.flush()

    def _get(row: list[str], ci: int | None) -> str:
        if ci is None or ci >= len(row):
            return ""
        return row[ci].strip()

    count = 0
    skip_first = True  # skip header row (first row)
    for row in rows_all:
        if skip_first:
            skip_first = False
            continue
        task_ref = _get(row, col_map["task_ref"])
        mpd_ref = _get(row, col_map["mpd_ref"])
        desc = _get(row, col_map["description"])
        if not task_ref and not mpd_ref and not desc:
            continue
        count += 1
        ws_row = WorkscopeImportRow(
            project_id=project_id,
            seq=count,
            source="pdf",
            task_ref=task_ref or None,
            mpd_ref=mpd_ref or None,
            description=desc or None,
            zone=_get(row, col_map["zone"]) or None,
            section=_get(row, col_map["section"]) or None,
            mh=_get(row, col_map["mh"]) or None,
            cost=_get(row, col_map["cost"]) or None,
        )
        db.add(ws_row)

    await db.commit()
    path.unlink(missing_ok=True)
    request.session.pop("ws_import", None)

    return templates.TemplateResponse(request, "workscope_import/result.html", {
        "project": project,
        "imported": count,
        "errors": [],
        "source": "pdf",
    })
