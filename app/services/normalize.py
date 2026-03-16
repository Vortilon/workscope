"""
Interval and applicability normalization. Preserve raw; produce normalized and machine-readable.
- 2YE vs 12YE; YR / YE / MO / FH / FC / C consistently.
"""
from __future__ import annotations
import re
from typing import Any


INTERVAL_UNITS = {"YR", "YE", "MO", "FH", "FC", "C", "DAY", "DAYS"}
UNIT_ALIASES = {"YR": "YR", "YE": "YE", "Y": "YR", "YRS": "YR", "YEARS": "YR", "MO": "MO", "MOS": "MO", "MONTHS": "MO", "FH": "FH", "FC": "FC", "CY": "C", "C": "C", "DAY": "DAY", "DAYS": "DAY"}


def normalize_interval_raw(raw: str | None) -> tuple[str, dict[str, Any] | None]:
    """
    Return (normalized_string, interval_json). Distinguish 2YE from 12YE etc.
    interval_json e.g. {"value": 24, "unit": "MO"} or {"value": 2, "unit": "YE"}.
    """
    if not raw or not isinstance(raw, str):
        return (raw or "", None)
    s = raw.strip().upper()
    # e.g. 24MO, 2YE, 12YE, 6000 FH, 12000 FC
    m = re.match(r"^(\d+(?:\.\d+)?)\s*([A-Z]+)$", s.replace(" ", ""))
    if not m:
        return (raw, None)
    value_str, unit = m.group(1), m.group(2)
    try:
        value = int(float(value_str))
    except ValueError:
        return (raw, None)
    unit_norm = UNIT_ALIASES.get(unit) or (unit if unit in INTERVAL_UNITS else None)
    if not unit_norm:
        return (raw, None)
    # 2YE vs 12YE: keep as-is in normalized string
    norm_str = f"{value}{unit_norm}"
    return (norm_str, {"value": value, "unit": unit_norm})


def normalize_applicability_tokens(raw: str | None) -> list[str]:
    """Tokenize applicability text (e.g. PRE XXX, POST YYY AND CFM56) into list of tokens. Preserve logic in engine."""
    if not raw:
        return []
    tokens = []
    s = raw.upper().replace("\n", " ").strip()
    # Simple split on AND/OR and whitespace; keep PRE/POST + following id
    for part in re.split(r"\s+AND\s+|\s+OR\s+", s):
        part = part.strip()
        if part:
            tokens.append(part)
    return tokens
