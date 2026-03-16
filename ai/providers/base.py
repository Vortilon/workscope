"""Abstract AI provider. All calls must receive only sanitized payloads."""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any


class BaseAIProvider(ABC):
    @abstractmethod
    async def complete(self, system_prompt: str, user_content: str | dict[str, Any], max_tokens: int = 500) -> str:
        """Return model response text. Inputs must already be sanitized."""
        pass

    @abstractmethod
    async def structure_suggestion(self, sanitized_payload: dict[str, Any]) -> dict[str, Any]:
        """Suggest column/structure mapping from sanitized sample. Returns e.g. {task_ref: 0, ...}."""
        pass
