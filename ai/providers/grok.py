"""Grok API adapter. All inputs must be sanitized by caller."""
from __future__ import annotations
from typing import Any
import httpx

from app.config import GROK_API_KEY
from ai.providers.base import BaseAIProvider
from ai.prompt_templates import STRUCTURE_DETECTION_SYSTEM


class GrokProvider(BaseAIProvider):
    def __init__(self, api_key: str | None = None):
        self._api_key = api_key or GROK_API_KEY
        self._base = "https://api.x.ai/v1"

    async def complete(self, system_prompt: str, user_content: str | dict[str, Any], max_tokens: int = 500) -> str:
        if not self._api_key:
            return ""
        payload = {
            "model": "grok-2-latest",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content if isinstance(user_content, str) else str(user_content)},
            ],
            "max_tokens": max_tokens,
        }
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{self._base}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
                json=payload,
                timeout=30.0,
            )
            if r.status_code != 200:
                return ""
            data = r.json()
            choices = data.get("choices", [])
            if not choices:
                return ""
            return choices[0].get("message", {}).get("content", "")

    async def structure_suggestion(self, sanitized_payload: dict[str, Any]) -> dict[str, Any]:
        if not self._api_key:
            return {}
        import json
        user_content = json.dumps(sanitized_payload)
        out = await self.complete(STRUCTURE_DETECTION_SYSTEM, user_content, max_tokens=400)
        try:
            return json.loads(out) if out else {}
        except json.JSONDecodeError:
            return {}
