"""Perkins AI proxy — server-to-server relay so the browser never calls Perkins directly."""
from __future__ import annotations

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.config import PERKINS_SERVICE_KEY, PERKINS_URL

router = APIRouter(prefix="/api/perkins", tags=["perkins"])

_TIMEOUT = 550.0


class PerkinsQuery(BaseModel):
    query: str
    dataset_id: int | None = None
    context: str = ""


def _headers() -> dict[str, str]:
    h: dict[str, str] = {"Content-Type": "application/json"}
    if PERKINS_SERVICE_KEY:
        h["X-API-Key"] = PERKINS_SERVICE_KEY
    return h


@router.post("/query")
async def proxy_query(body: PerkinsQuery, request: Request):
    """Relay a query to Perkins and return the answer. Requires a logged-in session."""
    if not request.session.get("user"):
        raise HTTPException(status_code=401, detail="Login required")
    if not PERKINS_URL:
        raise HTTPException(status_code=503, detail="Perkins integration not configured")

    payload = body.model_dump()
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            r = await client.post(
                f"{PERKINS_URL}/api/service/query",
                json=payload,
                headers=_headers(),
            )
            r.raise_for_status()
            return r.json()
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Perkins took too long to respond")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Perkins error: {e.response.status_code}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Could not reach Perkins: {e!s}")
