"""OpenAI adapter (stub). Use only with sanitized inputs."""
from __future__ import annotations
from typing import Any

from ai.providers.base import BaseAIProvider


class OpenAIProvider(BaseAIProvider):
    def __init__(self, api_key: str):
        self._api_key = api_key

    async def complete(self, system_prompt: str, user_content: str | dict[str, Any], max_tokens: int = 500) -> str:
        # Stub: integrate openai package when needed; ensure user_content is sanitized.
        return ""

    async def structure_suggestion(self, sanitized_payload: dict[str, Any]) -> dict[str, Any]:
        return {}
