"""
Interval and applicability normalization for ATR, Airbus, and Boeing MPDs.

Unit conventions per manufacturer
──────────────────────────────────
ATR 72:
  • Combined threshold/interval column: "T: 4000 FH  I: 2000 FH OR I: 2 YE"
  • Interval-only:  "I: 2400 FH", "I: NR", "I: WY", "I: 2 C"
  • Special: S: (sample %) and Tc: (total-cycle limit) may follow I: in the same cell
  • Units: FH, FC, C (cycles), YE, MO, DY, WY (weekly)
  • Special values: NR (No Requirement), A (At Installation)

Airbus A318/A319/A320/A321:
  • Separate SAMPLE THRESHOLD / SAMPLE INTERVAL / 100% THRESHOLD / 100% INTERVAL columns
  • Multiple OR conditions separated by explicit newline+OR: "12 YE\nOR\n24000 FC\nOR\n48000 FH"
  • Units: FH, FC, YE, MO, DY
  • Applicability: compound lines per aircraft type then PRE/POST MSN:
      "A318\nPOST 20071 (26-1048), (26-1121)\nPRE 34678\nOR\nA319\nPOST 20071 …"
    Parenthetical SB refs "(26-1048)" are stripped when tokenising.

Boeing 737 NG/MAX:
  • One INTERVAL column; threshold sub-column labeled THRES. in first data row
  • Multiple OR conditions separated by PLAIN NEWLINES (no OR keyword):
      "36000 FC\n12 YR\nNOTE"  →  ["36000 FC", "__OR__", "12 YR"]
  • Units: FH, FC, YR (not YE), MO, DY, DY
  • Applicability: one model code per line "600\n700\n800\n900ER"  (already handled)
"""
from __future__ import annotations
import re
from typing import Any

# ── Unit tables ───────────────────────────────────────────────────────────────

# Canonical unit names used internally
INTERVAL_UNITS = {"FH", "FC", "C", "YR", "YE", "MO", "DY", "WY", "HR"}

# Raw text → canonical unit.  Lower-case keys are intentional (input is .upper()d).
UNIT_ALIASES: dict[str, str] = {
    # ── Flight hours ───────────────────────────────────────────────────────
    "FH": "FH", "FLH": "FH", "FLT HRS": "FH", "FLTHRS": "FH",
    "HR": "FH", "HRS": "FH", "HOURS": "FH",
    # ── Flight cycles ──────────────────────────────────────────────────────
    "FC": "FC", "CYCS": "FC",
    # ── Generic cycles (ATR) ───────────────────────────────────────────────
    "C": "C", "CY": "C",
    # ── Calendar years ─────────────────────────────────────────────────────
    "YR": "YR", "YRS": "YR", "YEAR": "YR", "YEARS": "YR",   # Boeing
    "YE": "YE",                                               # Airbus / ATR
    # ── Months ─────────────────────────────────────────────────────────────
    "MO": "MO", "MOS": "MO", "MON": "MO", "MONTH": "MO", "MONTHS": "MO",
    "MT": "MO",   # variant used in some workscopes
    # ── Days ───────────────────────────────────────────────────────────────
    "DY": "DY", "DAY": "DY", "DAYS": "DY",
    # ── Weeks (ATR WY = weekly) ────────────────────────────────────────────
    "WY": "WY", "WK": "WY", "WEEK": "WY", "WEEKS": "WY",
}

# Special non-numeric interval values that are valid and should be kept as-is.
SPECIAL_INTERVAL_VALUES = {"NR", "A", "WY"}

# ── Regex patterns ────────────────────────────────────────────────────────────

_T_PREFIX  = re.compile(r'^T\s*:\s*', re.IGNORECASE)
_I_PREFIX  = re.compile(r'^I\s*:\s*', re.IGNORECASE)
# ATR-specific informational prefixes — keep visible in bubble display
_S_PREFIX  = re.compile(r'^S\s*:\s*', re.IGNORECASE)   # sample percentage
_TC_PREFIX = re.compile(r'^Tc\s*:\s*', re.IGNORECASE)  # total-cycle limit

_OR_SEP    = re.compile(r'\bOR\b', re.IGNORECASE)
# Combined "T: … I: …" cell
_T_THEN_I  = re.compile(r'^T\s*:\s*(.*?)\s+I\s*:\s*(.*)', re.IGNORECASE | re.DOTALL)
# Cell that begins with "I:" (interval-only)
_STARTS_I  = re.compile(r'^I\s*:', re.IGNORECASE)

# Parenthetical SB/mod references like "(26-1048)" or "(26-1BQW)" in Airbus applicability
_PAREN_REF = re.compile(r'\s*\([^)]{1,20}\)', re.IGNORECASE)

# NOTE keyword — drop from interval/threshold tokens
_NOTE_KW   = re.compile(r'\bNOTE\b', re.IGNORECASE)

# Compound-phrase keywords for applicability (ATR/Airbus)
_COMPOUND_KW = re.compile(
    r'\b(PRE|POST|SB|MSN|FROM|TO|THRU|THROUGH|BLK|BLOCK|CONFIG'
    r'|WITH|WITHOUT|INCORP|INCORPORATING|APPLICABLE|ALL'
    r'|CFM|IAE|PWA|GE|LEAP|PW|ETOPS|P/N|IF|EXCEPT)\b',
    re.IGNORECASE,
)
_NOTE_APPLIC_KW = re.compile(r'\bNOTE\b', re.IGNORECASE)


# ── Core split helpers ────────────────────────────────────────────────────────

def _strip_ti_prefix(s: str) -> str:
    """Remove leading T: or I: prefix.
    S: and Tc: are kept because they are informative labels (sample %, total-cycle limit)."""
    s = _T_PREFIX.sub('', s)
    s = _I_PREFIX.sub('', s)
    return s.strip()


def split_combined_ti(raw: str) -> tuple[str, str]:
    """Split raw into (threshold_part, interval_part).

    Handles:
      "T: X I: Y"  → (X, Y)          ATR combined format
      "I: Y"       → ("", Y)          interval-only cell
      anything else → (raw, "")       plain value — caller decides which field
    """
    if not raw:
        return "", ""
    s = raw.strip()
    # Combined T:/I: in one cell (ATR format; may span multiple lines via DOTALL)
    m = _T_THEN_I.match(s)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    # Cell starts with I: — it is purely an interval value
    if _STARTS_I.match(s):
        return "", _I_PREFIX.sub('', s).strip()
    return s, ""


# ── Tokeniser ─────────────────────────────────────────────────────────────────

def _tokenize_with_or(s: str) -> list[str]:
    """Split threshold/interval string into display tokens separated by '__OR__'.

    Separator logic (all three manufacturers):
      • Explicit OR keyword  →  always an OR separator
      • Plain newline        →  implicit OR separator (Boeing format)
      • Comma / semicolon   →  implicit OR separator within a single cell
    NOTE tokens are silently dropped.
    T:/I: prefixes are stripped; S: and Tc: prefixes are KEPT for display context.
    """
    s = s.strip()
    if not s:
        return []

    result: list[str] = []

    def _add(tok: str) -> None:
        tok = tok.strip()
        if not tok:
            return
        # Drop bare NOTE tokens
        if _NOTE_KW.fullmatch(tok):
            return
        # Insert implicit OR between consecutive real tokens
        if result and result[-1] != "__OR__":
            result.append("__OR__")
        result.append(tok)

    # First split on the explicit OR keyword (may be wrapped in newlines/spaces)
    or_parts = _OR_SEP.split(s)
    for idx, part in enumerate(or_parts):
        if idx > 0:
            # Explicit OR — mark it, but only if we already have a real token before
            if result and result[-1] != "__OR__":
                result.append("__OR__")
            elif not result:
                pass  # leading OR — ignore

        # Within each OR-part, newlines and commas/semicolons are implicit OR separators
        # (Boeing uses plain newlines; Airbus uses explicit OR between its sub-values)
        for sub in re.split(r'[\n;,]', part):
            _add(_strip_ti_prefix(sub))

    # Clean up stray leading/trailing markers
    while result and result[0] == "__OR__":
        result.pop(0)
    while result and result[-1] == "__OR__":
        result.pop()

    return result


# ── Public extraction API ─────────────────────────────────────────────────────

def extract_threshold_part(raw: str | None) -> str | None:
    """Extract threshold portion, handling ATR combined T:/I: cells and plain values."""
    if not raw:
        return None
    s = raw.strip()
    t_part, i_part = split_combined_ti(s)
    if i_part:
        return t_part or None
    # Standalone — strip T: prefix if present (leaves value clean)
    return _T_PREFIX.sub("", s).strip() or None


def extract_interval_part(raw: str | None) -> str | None:
    """Extract interval portion, handling ATR combined T:/I: cells, I:-only cells,
    and plain interval values."""
    if not raw:
        return None
    s = raw.strip()
    t_part, i_part = split_combined_ti(s)
    if i_part:
        return i_part or None
    # Standalone — strip I: prefix if present
    cleaned = _I_PREFIX.sub('', s).strip()
    return cleaned or None


def threshold_tokens(raw: str | None) -> list[str]:
    """Return display tokens for threshold with '__OR__' separators."""
    part = extract_threshold_part(raw)
    if not part:
        return []
    return _tokenize_with_or(part)


def interval_tokens(raw: str | None) -> list[str]:
    """Return display tokens for interval with '__OR__' separators."""
    part = extract_interval_part(raw)
    if not part:
        return []
    return _tokenize_with_or(part)


def parse_interval_tokens(raw: str | None) -> list[str]:
    """Legacy alias — delegates to _tokenize_with_or with T:/I: stripping."""
    if not raw:
        return []
    return _tokenize_with_or(_strip_ti_prefix(raw.strip()))


# ── Interval normalisation (for storage / comparison) ─────────────────────────

def normalize_interval_raw(raw: str | None) -> tuple[str, dict[str, Any] | None]:
    """Return (normalized_string, interval_json) for a single simple interval token.
    Only normalises tokens of the form "<number> <unit>" or "<number><unit>".
    Returns (raw, None) for complex / multi-value strings.

    interval_json e.g. {"value": 24, "unit": "MO"} or {"value": 4000, "unit": "FH"}.
    """
    if not raw or not isinstance(raw, str):
        return (raw or "", None)
    s = raw.strip().upper()
    # Try to match a simple "VALUE UNIT" token
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


# ── Applicability / effectivity tokeniser ────────────────────────────────────

def normalize_applicability_tokens(raw: str | None) -> list[str]:
    """Tokenize applicability/effectivity text into individual condition tokens.

    Manufacturer-specific handling:
      Boeing:  "600\\n700\\n800BCF\\n900ER"             → newlines become spaces,
               Boeing-style space-separated codes → ["600","700","800BCF","900ER"]
      ATR:     "POST 7696"  /  "PRE 10246"  /  compound PRE/POST blocks kept whole
      Airbus:  "A318\\nPOST 20071 (26-1048)\\nPRE 34678\\nOR\\nA319\\n…"
               Parenthetical SB refs stripped; compound blocks kept whole

    Tokens that contain "NOTE" are silently dropped.
    "ALL" tokens are excluded (not useful for crosscheck).
    """
    if not raw:
        return []

    # Strip parenthetical SB/mod references  "(26-1048)"  from Airbus text
    s = _PAREN_REF.sub(' ', raw)

    # Collapse newlines to spaces — this converts Boeing per-line codes to
    # space-separated form and flattens Airbus compound blocks properly
    s = s.upper().replace("\n", " ").strip()
    # Clean up residual double-spaces and stray commas/semicolons after paren removal
    s = re.sub(r'[,;]+', ' ', s)
    s = re.sub(r' {2,}', ' ', s).strip()

    tokens: list[str] = []

    for part in re.split(r'\s+AND\s+|\s+OR\s+', s):
        part = part.strip()
        if not part or part == "ALL":
            continue
        # Drop NOTE parts
        if _NOTE_APPLIC_KW.search(part):
            # Strip everything from NOTE onward (may have real codes before it)
            before_note = _NOTE_APPLIC_KW.split(part)[0].strip()
            # If compound phrase, keep cleaned version (but still drop ALL-only)
            if before_note and _COMPOUND_KW.search(before_note):
                # Remove stray trailing chars
                clean = re.sub(r'[,;\s]+$', '', before_note).strip()
                if clean and clean != "ALL":
                    tokens.append(clean)
            # If Boeing-style codes before NOTE, split and add them
            elif before_note:
                for code in before_note.split():
                    code = code.strip(' ,;')
                    if code and code != "ALL":
                        tokens.append(code)
            continue

        if _COMPOUND_KW.search(part):
            # ATR/Airbus compound phrase — keep as one token (remove stray trailing chars)
            clean = re.sub(r'[,;\s]+$', '', part).strip()
            if clean:
                tokens.append(clean)
        elif " " in part:
            # Boeing-style or similar: space-separated short codes
            for code in part.split():
                code = code.strip(' ,;')
                if code and code != "ALL" and not _NOTE_APPLIC_KW.match(code):
                    tokens.append(code)
        else:
            tokens.append(part)

    return tokens
