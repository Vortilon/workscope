"""
Matching engine: 1:1 task matching only. No hallucinations.
Layers: A exact deterministic, B normalized exact, C pattern-based, D AI-assisted (sanitized), E user confirmation.
"""
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete

from app.models.mpd import MPDTask
from app.models.workscope import ParsedWorkscopeRow, WorkscopeMatch
from app.models.project import Project


async def exact_match(
    session: AsyncSession,
    project_id: int,
    dataset_id: int,
) -> int:
    """
    For each ParsedWorkscopeRow of project, try exact task_reference match in MPDTask.
    Create WorkscopeMatch with reason and confidence. Returns count of matches created.
    """
    result = await session.execute(
        select(ParsedWorkscopeRow).where(ParsedWorkscopeRow.project_id == project_id)
    )
    rows = result.scalars().all()
    tasks_result = await session.execute(
        select(MPDTask).where(MPDTask.dataset_id == dataset_id)
    )
    mpd_tasks = {t.task_reference: t for t in tasks_result.scalars().all() if t.task_reference}
    mpd_tasks_by_number = {t.task_number: t for t in tasks_result.scalars().all() if t.task_number}
    count = 0
    for pr in rows:
        ref = (pr.task_ref_raw or "").strip()
        if not ref:
            continue
        mpd_task = mpd_tasks.get(ref) or mpd_tasks_by_number.get(ref)
        if mpd_task:
            match = WorkscopeMatch(
                project_id=project_id,
                parsed_row_id=pr.id,
                mpd_task_id=mpd_task.id,
                match_type="exact",
                confidence=1.0,
                reason="Matched by exact task reference",
                applicability_status="TBC",
            )
            session.add(match)
            count += 1
    return count


async def normalized_match(
    session: AsyncSession,
    project_id: int,
    dataset_id: int,
) -> int:
    """Match on normalized task_reference (e.g. stripped, upper). Skip rows already matched."""
    from sqlalchemy import and_, exists
    subq = exists().where(
        and_(
            WorkscopeMatch.parsed_row_id == ParsedWorkscopeRow.id,
            WorkscopeMatch.project_id == project_id,
        )
    )
    result = await session.execute(
        select(ParsedWorkscopeRow)
        .where(ParsedWorkscopeRow.project_id == project_id)
        .where(~subq)
    )
    rows = result.scalars().all()
    tasks_result = await session.execute(
        select(MPDTask).where(MPDTask.dataset_id == dataset_id)
    )
    norm_key = lambda x: (x or "").strip().upper()
    mpd_by_norm = {norm_key(t.task_reference): t for t in tasks_result.scalars().all() if t.task_reference}
    count = 0
    for pr in rows:
        ref = norm_key(pr.task_ref_raw)
        if not ref:
            continue
        mpd_task = mpd_by_norm.get(ref)
        if mpd_task:
            match = WorkscopeMatch(
                project_id=project_id,
                parsed_row_id=pr.id,
                mpd_task_id=mpd_task.id,
                match_type="normalized",
                confidence=0.95,
                reason="Matched by normalized task reference",
                applicability_status="TBC",
            )
            session.add(match)
            count += 1
    return count


async def run_initial_matching(
    session: AsyncSession,
    project_id: int,
    dataset_id: int,
) -> dict[str, int]:
    """Run exact then normalized; return counts."""
    # Delete existing matches for this project so we don't duplicate
    await session.execute(delete(WorkscopeMatch).where(WorkscopeMatch.project_id == project_id))
    c1 = await exact_match(session, project_id, dataset_id)
    await session.flush()
    c2 = await normalized_match(session, project_id, dataset_id)
    return {"exact": c1, "normalized": c2}
