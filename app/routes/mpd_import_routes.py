"""MPD import wizard: upload → sheet selection → column mapping → run → result."""
from __future__ import annotations
import json
import uuid
from pathlib import Path

from fastapi import APIRouter, Request, Depends, Form, UploadFile, File
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import IMPORT_TEMP_DIR, BASE_DIR
from app.database import get_db
from app.routes.web import _require_login
from app.services.mpd_import import (
    create_dataset,
    set_dataset_done,
    get_workbook_sheets,
    get_default_sheet_indices,
    load_workbook_data,
    detect_header_row,
    STANDARD_FIELDS,
    import_mpd_excel_with_mapping,
)

# ── Saved manufacturer mappings ───────────────────────────────────────────────
_MAPPINGS_FILE = BASE_DIR / "data" / "manufacturer_mappings.json"


def _load_saved_mappings() -> dict:
    try:
        if _MAPPINGS_FILE.exists():
            return json.loads(_MAPPINGS_FILE.read_text())
    except Exception:
        pass
    return {}


def _save_manufacturer_mapping(manufacturer: str, column_map: dict) -> None:
    """Persist a manufacturer → {field: col_index} mapping for future re-use."""
    if not manufacturer or not column_map:
        return
    try:
        saved = _load_saved_mappings()
        saved[manufacturer] = column_map
        _MAPPINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
        _MAPPINGS_FILE.write_text(json.dumps(saved, indent=2))
    except Exception:
        pass


# ── Column letter helper ──────────────────────────────────────────────────────
def _col_letter(idx: int) -> str:
    """0-based column index → Excel-style letter (A, B, …, Z, AA, AB, …)"""
    result = ""
    n = idx + 1
    while n > 0:
        n, r = divmod(n - 1, 26)
        result = chr(65 + r) + result
    return result

router = APIRouter()
BASE = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE / "templates"))


def _import_path(import_id: str, ext: str = ".xlsx") -> Path:
    return IMPORT_TEMP_DIR / f"{import_id}{ext}"


@router.get("/mpd/import", response_class=HTMLResponse)
async def import_step_upload(request: Request):
    if (r := _require_login(request)):
        return r
    return templates.TemplateResponse(request, "mpd_import/upload.html", {"error": None})


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
            request, "mpd_import/upload.html",
            {"error": "Please select a file.", "manufacturer": manufacturer, "model": model, "revision": revision},
        )
    ext = Path(file.filename).suffix.lower()
    if ext not in {".xlsx", ".xls"}:
        return templates.TemplateResponse(
            request, "mpd_import/upload.html",
            {"error": "Only .xlsx and .xls files are supported.", "manufacturer": manufacturer, "model": model, "revision": revision},
        )
    import_id = uuid.uuid4().hex
    path = _import_path(import_id, ext)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = await file.read()
    path.write_bytes(content)
    request.session["mpd_import_id"] = import_id
    request.session["mpd_import_ext"] = ext
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
    path = _import_path(import_id, request.session.get("mpd_import_ext", ".xlsx"))
    if not path.exists():
        request.session.pop("mpd_import_id", None)
        return RedirectResponse("/mpd/import?error=expired", status_code=303)
    try:
        sheets = get_workbook_sheets(path)
    except Exception as e:
        return templates.TemplateResponse(
            request, "mpd_import/upload.html", {"error": f"Cannot read workbook: {e}"},
        )
    manufacturer = request.session.get("mpd_import_manufacturer", "")
    sheet_names = [s["name"] for s in sheets]
    default_indices = get_default_sheet_indices(sheet_names, manufacturer)
    return templates.TemplateResponse(
        request, "mpd_import/sheets.html",
        {
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
    path = _import_path(import_id, request.session.get("mpd_import_ext", ".xlsx"))
    if not path.exists():
        return RedirectResponse("/mpd/import?error=expired", status_code=303)

    # ── Load file ONCE — avoids repeated I/O for large Boeing/ATR files ───────
    try:
        all_sheets_data = load_workbook_data(path)   # [(name, rows), ...]
    except Exception:
        return RedirectResponse("/mpd/import/sheets", status_code=303)

    manufacturer = request.session.get("mpd_import_manufacturer", "")
    saved_map = _load_saved_mappings().get(manufacturer, {})

    sheets_with_headers = []
    for i in sheet_indices:
        i = int(i)
        if i < 0 or i >= len(all_sheets_data):
            continue
        name, raw_rows = all_sheets_data[i]

        # Detect header row from already-loaded data
        header_row_index = detect_header_row(raw_rows)

        # Raw headers from the detected header row
        hrow = raw_rows[header_row_index] if raw_rows else []
        headers_raw = [str(c).strip() if c is not None else f"Col{j}" for j, c in enumerate(hrow)]

        # Clean headers: strip newlines/tabs (common in merged Excel cells)
        headers_clean = [
            h.replace("\n", " ").replace("\r", " ").replace("\t", " ").strip() if h else ""
            for h in headers_raw
        ]

        # Heuristic suggestions from header text
        suggested = {}
        for _label, key in STANDARD_FIELDS:
            for hi, h in enumerate(headers_clean):
                if h and key.replace("_", " ").lower() in h.lower():
                    suggested[key] = hi
                    break
                if h and key.lower() in h.lower():
                    suggested[key] = hi
                    break

        # Saved manufacturer mapping overrides heuristic (only if col index still valid)
        for field_key, col_idx in saved_map.items():
            if col_idx < len(headers_clean):
                suggested[field_key] = col_idx

        col_letters = [_col_letter(j) for j in range(len(headers_clean))]

        # Preview rows (truncated strings) — still from the already-loaded raw_rows
        n_preview = max(30, header_row_index + 12)
        preview_rows = [
            [str(v)[:40] if v is not None else "" for v in row]
            for row in raw_rows[:n_preview]
        ]

        # Sample values — 5 rows below header
        sample_offset = header_row_index + 5
        if sample_offset < len(preview_rows):
            raw_sample = preview_rows[sample_offset]
        elif header_row_index + 1 < len(preview_rows):
            raw_sample = preview_rows[header_row_index + 1]
        else:
            raw_sample = []
        sample_values = [str(v)[:60] if v else "" for v in raw_sample]
        while len(sample_values) < len(headers_clean):
            sample_values.append("")

        # Column fill rates from preview data rows
        data_rows_preview = preview_rows[header_row_index + 1:]
        col_fill_rates: list[float] = []
        for j in range(len(headers_clean)):
            if not data_rows_preview:
                col_fill_rates.append(1.0)
            else:
                filled = sum(1 for r in data_rows_preview if j < len(r) and r[j] and str(r[j]).strip())
                col_fill_rates.append(round(filled / len(data_rows_preview), 2))

        total_data_rows = max(0, len(raw_rows) - header_row_index - 1)

        sheets_with_headers.append({
            "index": i,
            "name": name,
            "headers": headers_clean,
            "header_row_index": header_row_index,
            "suggested": suggested,
            "col_letters": col_letters,
            "preview_rows": preview_rows,
            "sample_values": sample_values,
            "col_fill_rates": col_fill_rates,
            "total_data_rows": total_data_rows,
            "saved_mapping_applied": bool(saved_map),
        })

    return templates.TemplateResponse(
        request, "mpd_import/mapping.html",
        {
            "standard_fields": STANDARD_FIELDS,
            "sheets_with_headers": sheets_with_headers,
            "manufacturer": manufacturer,
        },
    )


def _parse_mapping_from_form(form_keys: list[tuple[str, str]]) -> list[dict]:
    """Build sheet_configs from form keys map_SI_fieldKey=colIndex + headerrow_SI=rowIndex."""
    by_sheet: dict[int, dict[str, int]] = {}
    header_rows: dict[int, int] = {}
    for key, val in form_keys:
        if key.startswith("headerrow_"):
            try:
                si = int(key[len("headerrow_"):])
                header_rows[si] = int(val)
            except (ValueError, TypeError):
                pass
        elif key.startswith("map_"):
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
    return [
        {"sheet_index": si, "header_row_index": header_rows.get(si, 0), "column_map": cm}
        for si, cm in sorted(by_sheet.items())
    ]


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
    path = _import_path(import_id, request.session.get("mpd_import_ext", ".xlsx"))
    if not path.exists():
        return RedirectResponse("/mpd/import?error=expired", status_code=303)
    form = await request.form()
    form_keys = list(form.items())
    sheet_configs = _parse_mapping_from_form(form_keys)
    # Apply guessed header row indices from mapping form if present
    header_rows: dict[int, int] = {}
    for key, val in form_keys:
        if not key.startswith("headerrow_"):
            continue
        try:
            sheet_idx = int(key.split("_", 1)[1])
        except ValueError:
            continue
        try:
            header_rows[sheet_idx] = int(val)
        except (ValueError, TypeError):
            continue
    for cfg in sheet_configs:
        si = cfg.get("sheet_index", 0)
        if si in header_rows:
            cfg["header_row_index"] = header_rows[si]
    # Persist merged column map for this manufacturer (all sheets merged; last sheet wins on conflict)
    if manufacturer:
        combined_map: dict[str, int] = {}
        for cfg in sheet_configs:
            combined_map.update(cfg.get("column_map", {}))
        _save_manufacturer_mapping(manufacturer, combined_map)

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
    request.session.pop("mpd_import_ext", None)
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
    return templates.TemplateResponse(request, "mpd_import/result.html", {"result": result})
