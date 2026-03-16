"""
AI memory: reusable rules vs project-isolated data.
- RuleMemory: generic, sanitized, reusable across projects (no confidential data).
- ProjectMemory: isolated by project_id; never mixed with other aircraft.
"""
from __future__ import annotations
from typing import Any
from app.config import BASE_DIR

# In-memory MVP; later persist to DB or Redis with clear separation.
_rule_memory: list[dict[str, Any]] = []
_project_memory: dict[int, list[dict[str, Any]]] = {}


class RuleMemory:
    """Global reusable parsing/matching rules. Sanitized only."""

    @staticmethod
    def add(rule_type: str, pattern: str, metadata: dict[str, Any] | None = None) -> None:
        _rule_memory.append({"type": rule_type, "pattern": pattern, "metadata": metadata or {}})

    @staticmethod
    def get_all() -> list[dict[str, Any]]:
        return list(_rule_memory)

    @staticmethod
    def get_by_type(rule_type: str) -> list[dict[str, Any]]:
        return [r for r in _rule_memory if r.get("type") == rule_type]


class ProjectMemory:
    """Per-project session memory. Isolated by project_id."""

    @staticmethod
    def add(project_id: int, key: str, value: Any) -> None:
        if project_id not in _project_memory:
            _project_memory[project_id] = []
        _project_memory[project_id].append({"key": key, "value": value})

    @staticmethod
    def get(project_id: int) -> list[dict[str, Any]]:
        return list(_project_memory.get(project_id, []))

    @staticmethod
    def clear(project_id: int) -> None:
        _project_memory.pop(project_id, None)


class PromptContextBuilder:
    """Build context for AI prompts: inject only sanitized and rule memory."""

    @staticmethod
    def for_structure_detection(project_id: int | None, sheet_headers: list[str], row_sample: list[dict]) -> dict[str, Any]:
        rules = RuleMemory.get_by_type("column_mapping")
        from ai.sanitizer import sanitize_for_structure_inference
        payload = sanitize_for_structure_inference(sheet_headers, row_sample, "excel")
        payload["reusable_rules"] = rules
        return payload
