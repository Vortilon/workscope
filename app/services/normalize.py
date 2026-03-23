"""
Interval and applicability normalization. Preserve raw; produce normalized and machine-readable.
- 2YE vs 12YE; YR / YE / MO / FH / FC / C consistently.
- ATR combined format: 'T: 4000 FH I: 24 MO' → split into threshold / interval.
- OR-logic: 'I: 2000 FH OR I: 24 MO' → two tokens with __OR__ separator.
"""
from __future__ import annotations
import re
from typing import Any

INTERVAL_UNITS = {"YR", "YE", "MO", "FH", "FC", "C", "DAY", "DAYS"}
UNIT_ALIASES = {
    "YR": "YR", "YE": "YE", "Y": "YR", "YRS": "YR", "YEARS": "YR",
    "MO": "MO", "MOS": "MO", "MONTHS": "MO",
    "FH": "FH", "FC": "FC",
    "CY": "C", "C": "C",
    "DAY": "DAY", "DAYS": "DAY",
}

# ── Pattern matchers ──────────────────────────────────────────────────────────
_T_PREFIX   = re.compile(r'^T\s*:\s*', re.IGNORECASE)
_I_PREFIX   = re.compile(r'(^|\s)I\s*:\s*', re.IGNORECASE)
_OR_SEP     = re.compile(r'\bOR\b', re.IGNORECASE)
# Detect combined "T: ... I: ..." in one cell
_T_THEN_I   = re.compile(r'^T\s*:\s*(.*?)\s+I\s*:\s*(.*)', re.IGNORECASE | re.DOTALL)
# Detect cell that starts with I: (interval-only)
_STARTS_I   = re.compile(r'^I\s*:', re.IGNORECASE)


def _strip_ti_prefix(s: str) -> str:
    """Remove a leading T: or I: prefix."""
    s = _T_PREFIX.sub('', s)
    s = re.sub(r'^I\s*:\s*', '', s, flags=re.IGNORECASE)
    return s.strip()


def _tokenize_with_or(s: str) -> list[str]:
    """Split on OR (→ '__OR__' separator) and on commas/semicolons.
    Strips T:/I: prefixes from each sub-token."""
    s = s.strip()
    if not s:
        return []
    result: list[str] = []
    or_parts = _OR_SEP.split(s)
    for idx, part in enumerate(or_parts):
        if idx > 0:
            result.append("__OR__")
        for sub in re.split(r'[,;]', part):
            tok = _strip_ti_prefix(sub.strip())
            if tok:
                result.append(tok)
    return result


def split_combined_ti(raw: str) -> tuple[str, str]:
    """If raw contains 'T: ... I: ...' pattern, return (threshold, interval).
    Otherwise return (raw, '') so caller can decide which field it belongs to."""
    if not raw:
        return "", ""
    m = _T_THEN_I.match(raw.strip())
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return raw.strip(), ""


def extract_threshold_part(raw: str | None) -> str | None:
    """Extract just the threshold portion from raw string.
    Handles combined 'T: X I: Y' format and standalone 'T: X' format."""
    if not raw:
        return None
    s = raw.strip()
    t_part, i_part = split_combined_ti(s)
    if i_part:
        # Combined format — threshold is t_part
        return t_part or None
    # Standalone — strip T: prefix if present
    return _T_PREFIX.sub("", s).strip() or None


def extract_interval_part(raw: str | None) -> str | None:
    """Extract just the interval portion from raw string.
    Handles combined 'T: X I: Y' format and standalone 'I: X' or plain 'X' format."""
    if not raw:
        return None
    s = raw.strip()
    t_part, i_part = split_combined_ti(s)
    if i_part:
        # Combined format — interval is i_part
        return i_part or None
    # Standalone — strip I: prefix if present
    cleaned = re.sub(r'^I\s*:\s*', '', s, flags=re.IGNORECASE).strip()
    return cleaned or None


def threshold_tokens(raw: str | None) -> list[str]:
    """Return threshold tokens with '__OR__' separators.
    Handles ATR combined T:/I: cells: extracts only threshold portion."""
    part = extract_threshold_part(raw)
    if not part:
        return []
    return _tokenize_with_or(part)


def interval_tokens(raw: str | None) -> list[str]:
    """Return interval tokens with '__OR__' separators.
    Handles ATR combined T:/I: cells: extracts only interval portion."""
    part = extract_interval_part(raw)
    if not part:
        return []
    return _tokenize_with_or(part)


def parse_interval_tokens(raw: str | None) -> list[str]:
    """Legacy: split threshold/interval string into individual tokens.
    Now delegates to _tokenize_with_or with T:/I: stripping.
    Kept for backward compatibility."""
    if not raw:
        return []
    return _tokenize_with_or(_strip_ti_prefix(raw.strip()))


def normalize_interval_raw(raw: str | None) -> tuple[str, dict[str, Any] | None]:
    """Return (normalized_string, interval_json).
    Distinguish 2YE from 12YE etc.
    interval_json e.g. {"value": 24, "unit": "MO"} or {"value": 2, "unit": "YE"}.
    """
    if not raw or not isinstance(raw, str):
        return (raw or "", None)
    s = raw.strip().upper()
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
    norm_str = f"{value}{unit_norm}"
    return (norm_str, {"value": value, "unit": unit_norm})


def normalize_applicability_tokens(raw: str | None) -> list[str]:
    """Tokenize applicability text (e.g. PRE XXX, POST YYY AND CFM56) into list of tokens."""
    if not raw:
        return []
    tokens = []
    s = raw.upper().replace("\n", " ").strip()
    for part in re.split(r"\s+AND\s+|\s+OR\s+", s):
        part = part.strip()
        if part:
            tokens.append(part)
    return tokens
