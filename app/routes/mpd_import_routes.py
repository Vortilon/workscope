"""MPD import wizard: upload → sheet selection → column mapping → run → result."""
from __future__ import annotations
import json
import uuid
from pathlib import Path

from fastapi import APIRouter, Request, Depends, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import IMPORT_TEMP_DIR
from app.database import get_db
from app.routes.web import _require_login
from app.services.mpd_import import (
    create_dataset,
    set_dataset_done,
    get_workbook_sheets,
    get_sheet_headers,
    get_default_sheet_indices,
    STANDARD_FIELDS,
    import_mpd_excel_with_mapping,
)

router = APIRouter()
BASE = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE / "templates"))


def _import_path(import_id: str) -> Path:
    return IMPORT_TEMP_DIR / f"{import_id}.xlsx"


@router.get("/mpd/import", response_class=HTMLResponse)
async def import_step_upload(request: Request):
    if (r := _require_login(request)):
        return r
    return templates.TemplateResponse(
        "mpd_import/upload.html",
        {"request": request, "error": None},
    )


@router.post("/mpd/import/upload", response_class=HTMLResponse)
async def import_upload_post(
    request: Request,
    manufacturer: str = Form(...),
    model: str = Form(...),
    revision: str = Form(...),
    file: UploadFile = File(...),
):
    if (r := _require_login(request)):
        return r
    if not file.filename:
        return templates.TemplateResponse(
            "mpd_import/upload.html",
            {"request": request, "error": "Please select a file.", "manufacturer": manufacturer, "model": model, "revision": revision},
        )
    ext = Path(file.filename).suffix.lower()
    if ext != ".xlsx":
        return templates.TemplateResponse(
            "mpd_import/upload.html",
            {"request": request, "error": "Only .xlsx files are supported.", "manufacturer": manufacturer, "model": model, "revision": revision},
        )
    import_id = uuid.uuid4().hex
    path = _import_path(import_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = await file.read()
    path.write_bytes(content)
    request.session["mpd_import_id"] = import_id
    request.session["mpd_import_manufacturer"] = manufacturer
    request.session["mpd_import_model"] = model
    request.session["mpd_import_revision"] = revision
    return RedirectResponse("/mpd/import/sheets", status_code=303)


@router.get("/mpd/import/sheets", response_class=HTMLResponse)
async def import_step_sheets(request: Request):
    if (r := _require_login(request)):
        return r
    import_id = request.session.get("mpd_import_id")
    if not import_id:
        return RedirectResponse("/mpd/import", status_code=303)
    path = _import_path(import_id)
    if not path.exists():
        request.session.pop("mpd_import_id", None)
        return RedirectResponse("/mpd/import?error=expired", status_code=303)
    try:
        sheets = get_workbook_sheets(path)
    except Exception as e:
        return templates.TemplateResponse(
            "mpd_import/upload.html",
            {"request": request, "error": f"Cannot read workbook: {e}"},
        )
    manufacturer = request.session.get("mpd_import_manufacturer", "")
    sheet_names = [s["name"] for s in sheets]
    default_indices = get_default_sheet_indices(sheet_names, manufacturer)
    return templates.TemplateResponse(
        "mpd_import/sheets.html",
        {
            "request": request,
            "sheets": sheets,
            "default_indices": default_indices,
            "manufacturer": manufacturer,
            "model": request.session.get("mpd_import_model", ""),
            "revision": request.session.get("mpd_import_revision", ""),
        },
    )


@router.post("/mpd/import/sheets", response_class=HTMLResponse)
async def import_sheets_post(request: Request, selected: list[str] = Form([])):
    if (r := _require_login(request)):
        return r
    indices = []
    for s in selected:
        try:
            indices.append(int(s))
        except ValueError:
            pass
    if not indices:
        return RedirectResponse("/mpd/import/sheets?error=select", status_code=303)
    request.session["mpd_import_sheet_indices"] = indices
    return RedirectResponse("/mpd/import/mapping", status_code=303)


@router.get("/mpd/import/mapping", response_class=HTMLResponse)
async def import_step_mapping(request: Request):
    if (r := _require_login(request)):
        return r
    import_id = request.session.get("mpd_import_id")
    sheet_indices = request.session.get("mpd_import_sheet_indices")
    if not import_id or not sheet_indices:
        return RedirectResponse("/mpd/import", status_code=303)
    path = _import_path(import_id)
    if not path.exists():
        return RedirectResponse("/mpd/import?error=expired", status_code=303)
    try:
        all_sheets = get_workbook_sheets(path)
    except Exception:
        return RedirectResponse("/mpd/import/sheets", status_code=303)
    # Build per-sheet headers and suggest mapping (first column name match)
    sheets_with_headers = []
    for i in sheet_indices:
        i = int(i)
        if i < 0 or i >= len(all_sheets):
            continue
        name = all_sheets[i]["name"]
        headers = get_sheet_headers(path, i)
        # Suggest: for each STANDARD_FIELDS, find first header that contains the key
        suggested = {}
        for _label, key in STANDARD_FIELDS:
            for hi, h in enumerate(headers):
                if h and key.replace("_", " ").lower() in h.lower():
                    suggested[key] = hi
                    break
                if h and key.lower() in h.lower():
                    suggested[key] = hi
                    break
        sheets_with_headers.append({"index": i, "name": name, "headers": headers, "suggested": suggested})
    return templates.TemplateResponse(
        "mpd_import/mapping.html",
        {
            "request": request,
            "standard_fields": STANDARD_FIELDS,
            "sheets_with_headers": sheets_with_headers,
        },
    )


def _parse_mapping_from_form(form_keys: list[tuple[str, str]]) -> list[dict]:
    """Build sheet_configs from form keys mapping_sheetIndex_fieldKey = colIndex."""
    by_sheet: dict[int, dict[str, int]] = {}
    for key, val in form_keys:
        if not key.startswith("map_") or "_" not in key:
            continue
        parts = key[4:].split("_", 1)
        if len(parts) != 2:
            continue
        try:
            sheet_idx = int(parts[0])
            field_key = parts[1]
        except ValueError:
            continue
        if val is None or val == "" or val == "__skip__":
            continue
        try:
            col_idx = int(val)
        except (ValueError, TypeError):
            continue
        if sheet_idx not in by_sheet:
            by_sheet[sheet_idx] = {}
        by_sheet[sheet_idx][field_key] = col_idx
    return [{"sheet_index": si, "header_row_index": 0, "column_map": cm} for si, cm in sorted(by_sheet.items())]


@router.post("/mpd/import/run", response_class=HTMLResponse)
async def import_run(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    if (r := _require_login(request)):
        return r
    import_id = request.session.get("mpd_import_id")
    sheet_indices = request.session.get("mpd_import_sheet_indices")
    manufacturer = request.session.get("mpd_import_manufacturer", "")
    model = request.session.get("mpd_import_model", "")
    revision = request.session.get("mpd_import_revision", "")
    if not import_id or not sheet_indices:
        return RedirectResponse("/mpd/import", status_code=303)
    path = _import_path(import_id)
    if not path.exists():
        return RedirectResponse("/mpd/import?error=expired", status_code=303)
    form = await request.form()
    form_keys = list(form.items())
    sheet_configs = _parse_mapping_from_form(form_keys)
    ds = await create_dataset(db, manufacturer, model, revision, None, path.name)
    total, results = import_mpd_excel_with_mapping(db, ds.id, path, sheet_configs)
    await set_dataset_done(db, ds.id)
    await db.commit()
    # Clean up temp file
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass
    request.session.pop("mpd_import_id", None)
    request.session.pop("mpd_import_sheet_indices", None)
    request.session.pop("mpd_import_manufacturer", None)
    request.session.pop("mpd_import_model", None)
    request.session.pop("mpd_import_revision", None)
    request.session["mpd_import_result"] = {
        "dataset_id": ds.id,
        "manufacturer": manufacturer,
        "model": model,
        "revision": revision,
        "total": total,
        "results": results,
    }
    return RedirectResponse("/mpd/import/result", status_code=303)


@router.get("/mpd/import/result", response_class=HTMLResponse)
async def import_result(request: Request):
    if (r := _require_login(request)):
        return r
    result = request.session.pop("mpd_import_result", None)
    if not result:
        return RedirectResponse("/mpd", status_code=303)
    return templates.TemplateResponse(
        "mpd_import/result.html",
        {"request": request, "result": result},
    )
