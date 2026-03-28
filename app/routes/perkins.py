"""Perkins AI proxy — server-to-server relay so the browser never calls Perkins directly."""
from __future__ import annotations

import time
from typing import Optional
import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.config import PERKINS_SERVICE_KEY, PERKINS_URL

router = APIRouter(prefix="/api/perkins", tags=["perkins"])

_TIMEOUT = 550.0


class PerkinsQuery(BaseModel):
    query: str
    dataset_id: Optional[int] = None
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


@router.post("/stream")
async def proxy_stream(body: PerkinsQuery, request: Request):
    """SSE streaming proxy — forwards Perkins /api/service/stream tokens to the browser.
    Tokens appear as they arrive from Ollama so there is never a timeout from the user's view.
    """
    if not request.session.get("user"):
        raise HTTPException(status_code=401, detail="Login required")
    if not PERKINS_URL:
        raise HTTPException(status_code=503, detail="Perkins integration not configured")

    async def _forward():
        import json as _json
        try:
            async with httpx.AsyncClient(timeout=600.0) as client:
                async with client.stream(
                    "POST",
                    f"{PERKINS_URL}/api/service/stream",
                    json=body.model_dump(),
                    headers=_headers(),
                ) as resp:
                    async for chunk in resp.aiter_text():
                        yield chunk
        except Exception as exc:
            yield f"data: {_json.dumps({'error': str(exc)})}\n\n"

    return StreamingResponse(
        _forward(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/health")
async def perkins_health(request: Request):
    """Test Perkins AI end-to-end: connectivity + first-token latency + full response time.
    Admin only. Returns JSON with status, timings, and the test answer.
    """
    import json as _json

    if not request.session.get("user"):
        raise HTTPException(status_code=401, detail="Login required")
    user_info = request.session.get("user", {})
    if not user_info.get("is_admin"):
        raise HTTPException(status_code=403, detail="Admin only")

    if not PERKINS_URL:
        return {"status": "unconfigured", "detail": "PERKINS_URL not set"}

    result: dict = {
        "perkins_url": PERKINS_URL,
        "status": "unknown",
        "connect_ok": False,
        "first_token_s": None,
        "total_s": None,
        "token_count": 0,
        "answer": "",
        "error": None,
    }

    t_start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{PERKINS_URL}/api/service/stream",
                json={"query": "What is an airworthiness directive? Answer in one sentence.",
                      "context": "", "dataset_id": None},
                headers=_headers(),
            ) as resp:
                result["connect_ok"] = True
                tokens: list[str] = []
                async for line in resp.aiter_lines():
                    line = line.strip()
                    if not line.startswith("data: "):
                        continue
                    try:
                        data = _json.loads(line[6:])
                    except Exception:
                        continue
                    if data.get("error"):
                        result["status"] = "error"
                        result["error"] = data["error"]
                        break
                    if data.get("token"):
                        if result["first_token_s"] is None:
                            result["first_token_s"] = round(time.monotonic() - t_start, 1)
                        tokens.append(data["token"])
                        result["token_count"] += 1
                    if data.get("done"):
                        result["total_s"] = round(time.monotonic() - t_start, 1)
                        result["answer"] = "".join(tokens)
                        result["status"] = "ok"
                        break

        if result["status"] == "unknown":
            result["status"] = "timeout_or_no_done"
            result["total_s"] = round(time.monotonic() - t_start, 1)
            result["answer"] = "".join(tokens) if "tokens" in dir() else ""

    except httpx.ConnectError as exc:
        result["status"] = "unreachable"
        result["error"] = str(exc)
    except httpx.TimeoutException:
        result["status"] = "timeout"
        result["total_s"] = round(time.monotonic() - t_start, 1)
        result["error"] = "Request timed out after 120s"
    except Exception as exc:
        result["status"] = "error"
        result["error"] = str(exc)

    return result
