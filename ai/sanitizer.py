"""
Sanitization layer: ensure only safe, non-confidential data is sent to external AI.
- Input: raw snippets, field labels, structural samples, non-sensitive task fragments.
- Never: serial numbers, registration, operator IDs, confidential customer data.
- Log what was sanitized and sent (audit_log).
"""
from __future__ import annotations
from typing import Any
from app.config import BASE_DIR
from ai.redaction import redact_for_ai


def sanitize_task_fragment(text: str | None, max_chars: int = 500) -> str:
    """For AI structure inference only: short, redacted fragment."""
    if not text:
        return ""
    from ai.redaction import redact_string
    cleaned = redact_string(str(text))[:max_chars]
    return cleaned


def sanitize_column_sample(column_name: str, sample_values: list[str], max_per_col: int = 5) -> dict[str, Any]:
    """Produce a safe sample for column-type inference. No real MSN/serial/reg."""
    from ai.redaction import redact_string
    safe = [redact_string(v) for v in sample_values[:max_per_col]]
    return {"column": column_name, "sample_values": safe}


def sanitize_for_structure_inference(
    sheet_headers: list[str],
    row_sample: list[dict[str, Any]],
    file_type: str,
) -> dict[str, Any]:
    """
    Build payload for AI-assisted structure/column detection only.
    All values in row_sample must be redacted.
    """
    payload = {
        "file_type": file_type,
        "headers": sheet_headers,
        "row_sample": redact_for_ai(row_sample),
    }
    return payload


def log_sanitized_sent(action: str, summary: str, entity_type: str | None = None, entity_id: str | None = None) -> None:
    """Record in audit log what was sanitized and sent to AI (no raw data). Caller may pass DB session for sync write."""
    # MVP: append to local file; later wire to AuditLog in request/session.
    try:
        log_path = BASE_DIR / "data" / "audit_ai_sanitized.log"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a") as f:
            f.write(f"{action}\t{entity_type or ''}\t{entity_id or ''}\t{summary[:500]}\n")
    except Exception:
        pass
