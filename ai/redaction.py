"""
Redact proprietary and confidential data before any payload leaves the app.
CRITICAL: No serial numbers, registration, operator-specific IDs, or customer data may be sent.
"""
from __future__ import annotations
import re
from typing import Any

# Patterns that indicate confidential data – extend as needed; never relax.
SERIAL_LIKE = re.compile(r"\b\d{4,}\b|\b[A-Z]{2,}\d{4,}\b", re.I)
REG_LIKE = re.compile(r"\b[A-Z]{2}-[A-Z]{3}\b|\bN\d{1,5}[A-Z]{0,2}\b", re.I)
# Generic placeholder for redacted values
REDACTED = "[REDACTED]"


def redact_string(value: str | None) -> str:
    if not value or not isinstance(value, str):
        return ""
    # Replace serial-like numbers
    out = SERIAL_LIKE.sub(REDACTED, value)
    out = REG_LIKE.sub(REDACTED, out)
    return out


def redact_dict(d: dict[str, Any], keys_to_redact: set[str] | None = None) -> dict[str, Any]:
    """Redact known sensitive keys and serial-like values in strings."""
    sensitive = keys_to_redact or {
        "msn", "serial", "registration", "tail_number", "operator", "customer",
        "tsn", "csn", "aircraft_id", "ac_id", "owner",
    }
    out = {}
    for k, v in d.items():
        key_lower = k.lower() if isinstance(k, str) else ""
        if key_lower in sensitive or "serial" in key_lower or "registration" in key_lower:
            out[k] = REDACTED
        elif isinstance(v, str):
            out[k] = redact_string(v)
        elif isinstance(v, dict):
            out[k] = redact_dict(v, keys_to_redact=sensitive)
        elif isinstance(v, list):
            out[k] = [redact_string(x) if isinstance(x, str) else redact_dict(x, keys_to_redact=sensitive) if isinstance(x, dict) else x for x in v]
        else:
            out[k] = v
    return out


def redact_for_ai(payload: dict[str, Any] | list | str) -> Any:
    """Single entry point: sanitize payload for external AI. Log what was sent (summary only)."""
    if isinstance(payload, str):
        return redact_string(payload)
    if isinstance(payload, list):
        return [redact_for_ai(x) for x in payload]
    if isinstance(payload, dict):
        return redact_dict(payload)
    return payload
