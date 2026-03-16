"""
Workscope import: detect file type, extract sheets/pages, identify columns and task rows.
Store ParsedWorkscopeRow; present candidate mappings for user confirmation.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.project import ProjectFile
from app.models.workscope import ParsedWorkscopeRow


def detect_file_type(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext in (".xlsx", ".xls"):
        return "excel"
    if ext == ".pdf":
        return "pdf"
    return "unknown"


def _excel_headers_and_rows(file_path: Path, sheet_index: int = 0) -> tuple[list[str], list[list]]:
    import openpyxl
    wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
    sheet = wb.worksheets[sheet_index]
    rows = list(sheet.iter_rows(values_only=True))
    wb.close()
    if not rows:
        return [], []
    headers = [str(c).strip() if c is not None else f"Col{i}" for i, c in enumerate(rows[0])]
    return headers, rows[1:]


def detect_columns_heuristic(headers: list[str], rows: list[list]) -> dict[str, str | int]:
    """
    Heuristic: guess task_ref, service_check, description, reference by header name and sample.
    Returns e.g. {"task_ref": 0, "description": 2} (index or header name).
    LATER AI: optional AI-assisted structure detection (sanitized payload only) can override or refine.
    """
    mapping = {}
    for i, h in enumerate(headers):
        if not h:
            continue
        hl = h.lower()
        if "task" in hl and "ref" in hl or "task" in hl and "number" in hl:
            mapping["task_ref"] = i
        elif "service" in hl or "check" in hl:
            mapping["service_check"] = i
        elif "desc" in hl or "title" in hl:
            mapping["description"] = i
        elif "ref" in hl or "mpd" in hl or "cross" in hl:
            mapping["reference"] = i
    return mapping


async def parse_workscope_excel(
    session: AsyncSession,
    project_id: int,
    project_file_id: int,
    file_path: Path,
    sheet_index: int = 0,
    column_mapping: dict[str, int] | None = None,
) -> int:
    """
    Parse Excel workscope into ParsedWorkscopeRow. If column_mapping not provided, use heuristic.
    Returns row count.
    """
    headers, rows = _excel_headers_and_rows(file_path, sheet_index)
    if not headers:
        return 0
    if column_mapping is None:
        mapping = detect_columns_heuristic(headers, rows)
        column_mapping = {k: v for k, v in mapping.items() if isinstance(v, int)}
    count = 0
    for row_index, row in enumerate(rows):
        task_ref = row[column_mapping["task_ref"]] if "task_ref" in column_mapping and column_mapping["task_ref"] < len(row) else None
        service_check = row[column_mapping["service_check"]] if "service_check" in column_mapping and column_mapping["service_check"] < len(row) else None
        description = row[column_mapping["description"]] if "description" in column_mapping and column_mapping["description"] < len(row) else None
        reference = row[column_mapping["reference"]] if "reference" in column_mapping and column_mapping["reference"] < len(row) else None
        raw_row = {headers[i]: (row[i] if i < len(row) else None) for i in range(len(headers))}
        row_type = "task" if task_ref or description else "unknown"
        pr = ParsedWorkscopeRow(
            project_id=project_id,
            project_file_id=project_file_id,
            row_index=row_index,
            sheet_index=sheet_index,
            task_ref_raw=str(task_ref).strip() if task_ref else None,
            service_check_raw=str(service_check).strip() if service_check else None,
            description_raw=str(description).strip() if description else None,
            reference_raw=str(reference).strip() if reference else None,
            raw_row_json=raw_row,
            row_type=row_type,
            confidence=0.8,
        )
        session.add(pr)
        count += 1
    return count


async def get_candidate_mapping(
    session: AsyncSession,
    file_path: Path,
    sheet_index: int = 0,
) -> dict[str, Any]:
    """Return detected columns and confidence for user confirmation."""
    headers, rows = _excel_headers_and_rows(file_path, sheet_index)
    mapping = detect_columns_heuristic(headers, rows)
    return {
        "headers": headers,
        "task_ref": mapping.get("task_ref"),
        "service_check": mapping.get("service_check"),
        "description": mapping.get("description"),
        "reference": mapping.get("reference"),
        "confidence": 0.8,
    }
