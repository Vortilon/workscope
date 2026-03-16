"""
MPD import: parse Excel (and later PDF), create MPDDataset + MPDTask.
Preserve raw values; create normalized interval and applicability.
"""
from __future__ import annotations
from pathlib import Path
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.mpd import MPDDataset, MPDTask
from app.services.normalize import normalize_interval_raw, normalize_applicability_tokens


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
    import openpyxl
    wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
    sheet = wb.worksheets[sheet_index]
    rows = list(sheet.iter_rows(values_only=True))
    wb.close()
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
