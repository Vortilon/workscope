"""
MPD import: parse Excel (and later PDF), create MPDDataset + MPDTask.
Preserve raw values; create normalized interval and applicability.
Multi-step UI: upload → sheet selection → column mapping → run import.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.mpd import MPDDataset, MPDTask
from app.services.normalize import normalize_interval_raw, normalize_applicability_tokens

# Standard fields shown in column-mapping UI (label, our key)
STANDARD_FIELDS = [
    ("Task reference", "task_reference"),
    ("Title", "title"),
    ("Description", "description"),
    ("Threshold", "threshold"),
    ("Interval", "interval"),
    ("Effectivity", "effectivity"),
    ("Job procedure", "job_procedure"),
    ("Zone", "zone"),
    ("MH Zone", "zone_mh"),
    ("Man", "man"),
    ("Access", "access"),
    ("MH Access", "access_mh"),
    ("MH Preparation", "preparation_mh"),
    ("Skill", "skill"),
    ("Equipment", "equipment"),
    ("Section", "section"),
    ("Chapter", "chapter"),
]

# Manufacturer default sheet names (first match wins)
DEFAULT_SHEETS = {
    "ATR": ["MPDTasks"],
    "Airbus": ["MPD"],
    "Boeing": [
        "SYSTEMS AND POWERPLANT MAINTENA",  # partial match
        "STRUCTURAL MAINTENANCE PROGRAM",
        "ZONAL INSPECTION PROGRAM",
    ],
}


def _load_wb_sheets(file_path: Path) -> list[tuple[str, list[list[Any]]]]:
    """
    Load all sheets from an .xlsx or .xls file.
    Returns list of (sheet_name, rows) where rows is list of list of cell values.
    """
    ext = file_path.suffix.lower()
    if ext == ".xls":
        import xlrd
        wb = xlrd.open_workbook(str(file_path))
        result = []
        for sheet in wb.sheets():
            rows = [sheet.row_values(r) for r in range(sheet.nrows)]
            result.append((sheet.name, rows))
        return result
    else:
        import openpyxl
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        result = [(ws.title, [list(r) for r in ws.iter_rows(values_only=True)]) for ws in wb.worksheets]
        wb.close()
        return result


def get_workbook_sheets(file_path: Path) -> list[dict[str, Any]]:
    """Return list of {index, name} for all sheets."""
    return [{"index": i, "name": name} for i, (name, _) in enumerate(_load_wb_sheets(file_path))]


def get_sheet_headers(file_path: Path, sheet_index: int, header_row_index: int = 0) -> tuple[list[str], int]:
    """Return (headers, header_row_index) for the sheet.

    Heuristic: if header_row_index is 0, scan the first few rows and pick the row
    with the most non-empty string-like cells as the header row. This helps when
    the true header is on row 2/3/etc (common in OEM MPDs).
    """
    sheets = _load_wb_sheets(file_path)
    if sheet_index >= len(sheets):
        return [], 0
    _, rows = sheets[sheet_index]
    if not rows:
        return [], 0
    guess_idx = header_row_index
    if header_row_index == 0:
        best_idx = 0
        best_score = -1
        max_rows = min(len(rows), 10)
        for idx in range(max_rows):
            row = rows[idx]
            score = sum(1 for cell in row if isinstance(cell, str) and cell.strip())
            if score > best_score:
                best_score = score
                best_idx = idx
        guess_idx = best_idx
    headers = [str(c).strip() if c is not None else f"Col{i}" for i, c in enumerate(rows[guess_idx])]
    return headers, guess_idx


def get_default_sheet_indices(sheet_names: list[str], manufacturer: str) -> list[int]:
    """Return list of sheet indices to select by default for this manufacturer."""
    candidates = DEFAULT_SHEETS.get(manufacturer, [])
    indices = []
    for i, name in enumerate(sheet_names):
        name_upper = name.upper()
        for c in candidates:
            if c.upper() in name_upper:
                indices.append(i)
                break
    if not indices and sheet_names:
        indices = [0]
    return indices


async def create_dataset(
    session: AsyncSession,
    manufacturer: str,
    model: str,
    revision: str,
    version: str | None,
    source_file: str | None,
) -> MPDDataset:
    ds = MPDDataset(
        manufacturer=manufacturer,
        model=model,
        revision=revision,
        version=version,
        source_file=source_file,
        parsed_status="in_progress",
    )
    session.add(ds)
    await session.flush()
    return ds


def _row_to_task_dict(row: list, headers: list[str]) -> dict:
    out = {}
    for i, h in enumerate(headers):
        if i < len(row):
            val = row[i]
            if hasattr(val, "strip"):
                val = val.strip() if val else ""
            else:
                val = str(val) if val is not None else ""
            out[h] = val
    return out


async def import_mpd_excel(
    session: AsyncSession,
    dataset_id: int,
    file_path: Path,
    sheet_index: int = 0,
    header_row_index: int = 0,
) -> int:
    """
    Parse Excel MPD and insert MPDTask rows. Preserve raw; set normalized fields.
    Returns count of tasks created.
    """
    sheets = _load_wb_sheets(file_path)
    if sheet_index >= len(sheets):
        return 0
    _, rows = sheets[sheet_index]
    if not rows:
        return 0
    headers = [str(c).strip() if c is not None else f"Col{i}" for i, c in enumerate(rows[header_row_index])]
    task_count = 0
    for idx in range(header_row_index + 1, len(rows)):
        row = list(rows[idx])
        row_dict = _row_to_task_dict(row, headers)
        # Map common column names to model fields (flexible keys)
        def get(*keys, default=""):
            for k in keys:
                for h in headers:
                    if h and k.lower() in h.lower():
                        return row_dict.get(h, default) or default
            return default

        task_ref = get("task_reference", "task_ref", "task number", "task no") or get("task")
        title = get("title", "description")
        desc = get("description", "details")
        section = get("section", "chapter")
        chapter = get("chapter", "section")
        threshold_raw = get("threshold", "interval")
        interval_raw = get("interval", "threshold")
        th_norm, th_json = normalize_interval_raw(threshold_raw)
        int_norm, int_json = normalize_interval_raw(interval_raw)
        applicability_raw = get("applicability", "effectivity")
        tokens = normalize_applicability_tokens(applicability_raw)
        applicability_tokens_normalized = ",".join(tokens) if tokens else None

        task = MPDTask(
            dataset_id=dataset_id,
            task_reference=task_ref or None,
            task_number=task_ref or None,
            task_code=task_ref or None,
            title=title or None,
            description=desc or None,
            section=section or None,
            chapter=chapter or None,
            threshold_raw=threshold_raw or None,
            interval_raw=interval_raw or None,
            threshold_normalized=th_norm or None,
            interval_normalized=int_norm or None,
            interval_json=int_json or th_json,
            applicability_raw=applicability_raw or None,
            applicability_tokens_normalized=applicability_tokens_normalized,
            row_index=idx,
            extra_raw=row_dict,
        )
        session.add(task)
        task_count += 1
    return task_count


async def set_dataset_done(session: AsyncSession, dataset_id: int) -> None:
    ds = (await session.execute(select(MPDDataset).where(MPDDataset.id == dataset_id))).scalars().one_or_none()
    if ds:
        ds.parsed_status = "done"


def _get_mapped_val(row: list, col_index: int | None) -> str:
    if col_index is None or col_index < 0 or col_index >= len(row):
        return ""
    val = row[col_index]
    if hasattr(val, "strip"):
        return (val.strip() or "") if val else ""
    return str(val) if val is not None else ""


def import_mpd_excel_with_mapping(
    session: AsyncSession,
    dataset_id: int,
    file_path: Path,
    sheet_configs: list[dict[str, Any]],
) -> tuple[int, list[dict[str, Any]]]:
    """
    sheet_configs: list of {sheet_index, header_row_index, column_map}.
    column_map: dict our_field -> col_index (0-based).
    Returns (total_task_count, list of {sheet_name, count, errors: [row, message]}).
    """
    all_sheets = _load_wb_sheets(file_path)
    total = 0
    results = []
    for cfg in sheet_configs:
        sheet_idx = cfg.get("sheet_index", 0)
        header_row = cfg.get("header_row_index", 0)
        column_map = cfg.get("column_map") or {}
        if sheet_idx >= len(all_sheets):
            results.append({"sheet_name": f"Sheet{sheet_idx}", "count": 0, "errors": [{"row": 0, "message": "Sheet index out of range"}]})
            continue
        sheet_name, rows = all_sheets[sheet_idx]
        if not rows:
            results.append({"sheet_name": sheet_name, "count": 0, "errors": []})
            continue
        headers = [str(c).strip() if c is not None else f"Col{i}" for i, c in enumerate(rows[header_row])]
        # Map our field keys to column indices
        def col(field_key: str) -> int | None:
            if field_key in column_map:
                return column_map[field_key]
            return None

        count = 0
        errors = []
        for idx in range(header_row + 1, len(rows)):
            row = list(rows[idx])
            try:
                task_ref = _get_mapped_val(row, col("task_reference")) or _get_mapped_val(row, col("title"))
                threshold_raw = _get_mapped_val(row, col("threshold"))
                interval_raw = _get_mapped_val(row, col("interval"))
                applicability_raw = _get_mapped_val(row, col("effectivity"))
                th_norm, th_json = normalize_interval_raw(threshold_raw or None)
                int_norm, int_json = normalize_interval_raw(interval_raw or None)
                tokens = normalize_applicability_tokens(applicability_raw or None)
                applicability_tokens_normalized = ",".join(tokens) if tokens else None

                task = MPDTask(
                    dataset_id=dataset_id,
                    task_reference=task_ref or None,
                    task_number=task_ref or None,
                    task_code=task_ref or None,
                    title=_get_mapped_val(row, col("title")) or None,
                    description=_get_mapped_val(row, col("description")) or None,
                    section=_get_mapped_val(row, col("section")) or None,
                    chapter=_get_mapped_val(row, col("chapter")) or None,
                    threshold_raw=threshold_raw or None,
                    interval_raw=interval_raw or None,
                    threshold_normalized=th_norm or None,
                    interval_normalized=int_norm or None,
                    interval_json=int_json or th_json,
                    applicability_raw=applicability_raw or None,
                    applicability_tokens_normalized=applicability_tokens_normalized,
                    job_procedure=_get_mapped_val(row, col("job_procedure")) or None,
                    zones=_get_mapped_val(row, col("zone")) or None,
                    zone_mh=_get_mapped_val(row, col("zone_mh")) or None,
                    man=_get_mapped_val(row, col("man")) or None,
                    access_items=_get_mapped_val(row, col("access")) or None,
                    access_mh=_get_mapped_val(row, col("access_mh")) or None,
                    preparation_mh=_get_mapped_val(row, col("preparation_mh")) or None,
                    skill=_get_mapped_val(row, col("skill")) or None,
                    equipment=_get_mapped_val(row, col("equipment")) or None,
                    row_index=idx,
                    extra_raw={h: _get_mapped_val(row, i) for i, h in enumerate(headers) if i < len(row)},
                )
                session.add(task)
                count += 1
                total += 1
            except Exception as e:
                errors.append({"row": idx + 1, "message": str(e)})
        results.append({"sheet_name": sheet_name, "count": count, "errors": errors})
    return total, results
