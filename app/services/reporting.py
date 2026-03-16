"""
Reporting: aggregate counts, clickable lists, plain-language reasons.
- Total tasks, matched, effective, omissions, extras, TBC, unmatched.
"""
from __future__ import annotations
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_

from app.models.workscope import ParsedWorkscopeRow, WorkscopeMatch
from app.models.mpd import MPDTask


async def get_report_summary(session: AsyncSession, project_id: int, dataset_id: int) -> dict:
    """
    Build report summary: total workscope tasks, matched, effective per check,
    effective not in workscope, extra in workscope not in MPD, TBC, unmatched.
    All counts are intended to be clickable to show task lists.
    """
    total_workscope = (
        await session.execute(
            select(func.count(ParsedWorkscopeRow.id)).where(
                and_(ParsedWorkscopeRow.project_id == project_id, ParsedWorkscopeRow.row_type == "task")
            )
        )
    ).scalar() or 0

    matched = (
        await session.execute(
            select(func.count(WorkscopeMatch.id)).where(
                and_(WorkscopeMatch.project_id == project_id, WorkscopeMatch.mpd_task_id.isnot(None))
            )
        )
    ).scalar() or 0

    effective = (
        await session.execute(
            select(func.count(WorkscopeMatch.id)).where(
                and_(
                    WorkscopeMatch.project_id == project_id,
                    WorkscopeMatch.applicability_status == "YES",
                )
            )
        )
    ).scalar() or 0

    tbc = (
        await session.execute(
            select(func.count(WorkscopeMatch.id)).where(
                and_(
                    WorkscopeMatch.project_id == project_id,
                    WorkscopeMatch.applicability_status == "TBC",
                )
            )
        )
    ).scalar() or 0

    unmatched = total_workscope - matched

    return {
        "total_workscope_tasks": total_workscope,
        "matched_with_mpd": matched,
        "effective_tasks": effective,
        "applicability_tbc": tbc,
        "unmatched_pending_review": unmatched,
        # Placeholders for Phase 2
        "effective_not_in_workscope": 0,
        "extra_in_workscope_not_in_mpd": 0,
        "not_required_for_selected_checks": 0,
    }


async def get_match_list(
    session: AsyncSession,
    project_id: int,
    filter_type: str | None = None,
) -> list[dict]:
    """Get list of matches with reason for drill-down. filter_type: matched | effective | tbc | unmatched."""
    q = select(WorkscopeMatch).where(WorkscopeMatch.project_id == project_id)
    if filter_type == "effective":
        q = q.where(WorkscopeMatch.applicability_status == "YES")
    elif filter_type == "tbc":
        q = q.where(WorkscopeMatch.applicability_status == "TBC")
    elif filter_type == "matched":
        q = q.where(WorkscopeMatch.mpd_task_id.isnot(None))
    result = await session.execute(q)
    matches = result.scalars().all()
    out = []
    for m in matches:
        out.append({
            "id": m.id,
            "parsed_row_id": m.parsed_row_id,
            "mpd_task_id": m.mpd_task_id,
            "match_type": m.match_type,
            "reason": m.reason or "No MPD match found",
            "applicability_status": m.applicability_status,
            "applicability_reason": m.applicability_reason,
        })
    return out
