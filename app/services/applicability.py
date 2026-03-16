"""
Applicability/effectivity engine. Use terms consistently.
- ALL always applies.
- Status: YES | NO | TBC. Default unresolved = TBC.
- TBC = treat as effective for safety, flagged in yellow/pending.
"""
from __future__ import annotations
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.mpd import MPDTask
from app.models.workscope import WorkscopeMatch


async def evaluate_task_applicability(
    session: AsyncSession,
    match_id: int,
    condition_answers: dict[str, str],
) -> str:
    """
    Evaluate applicability for one match given user/evidence condition_answers.
    condition_answers: {"PRE 33844": "YES", "CFM56": "YES", ...}
    Returns YES | NO | TBC.
    """
    result = await session.execute(select(WorkscopeMatch).where(WorkscopeMatch.id == match_id))
    match = result.scalars().one_or_none()
    if not match or not match.mpd_task_id:
        return "TBC"
    task_result = await session.execute(select(MPDTask).where(MPDTask.id == match.mpd_task_id))
    task = task_result.scalars().one_or_none()
    if not task:
        return "TBC"
    raw = (task.applicability_raw or "").strip().upper()
    if not raw or raw == "ALL":
        return "YES"
    # Simple AND logic: all tokens must resolve to YES
    tokens = [t.strip() for t in (task.applicability_tokens_normalized or "").split(",") if t.strip()]
    for token in tokens:
        ans = condition_answers.get(token, "TBC")
        if ans == "NO":
            return "NO"
        if ans == "TBC":
            return "TBC"
    return "YES"


async def set_match_applicability(
    session: AsyncSession,
    match_id: int,
    status: str,
    reason: str,
) -> None:
    """Set applicability_status and applicability_reason on WorkscopeMatch."""
    result = await session.execute(select(WorkscopeMatch).where(WorkscopeMatch.id == match_id))
    match = result.scalars().one_or_none()
    if match:
        match.applicability_status = status
        match.applicability_reason = reason
