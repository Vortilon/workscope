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
INTERVAL_UNITS = {"FH", "FC", "C", "LDG", "YR", "YE", "MO", "DY", "WY"}

# Raw text → canonical unit.
# Keys are UPPER-CASE (input is always .upper()d before lookup).
UNIT_ALIASES: dict[str, str] = {
    # ── Flight hours ───────────────────────────────────────────────────────
    "FH": "FH", "FLH": "FH", "FLT HRS": "FH", "FLTHRS": "FH",
    "HR": "FH", "HRS": "FH", "HOURS": "FH", "FLT": "FH",
    "EFH": "FH",   # equivalent flight hours (turboprop / helicopter)
    "BH": "FH",    # block hours (regional / turboprop operators)
    # ── Flight / landing cycles ────────────────────────────────────────────
    "FC": "FC", "CYCS": "FC",
    "LDG": "LDG", "LDGS": "LDG",   # landings — kept separate from FC for accuracy
    # ── Generic cycles (ATR) ───────────────────────────────────────────────
    "C": "C", "CY": "C",
    # ── Calendar years ─────────────────────────────────────────────────────
    "YR": "YR", "YRS": "YR", "YEAR": "YR", "YEARS": "YR",   # Boeing
    "YE": "YE",                                               # Airbus / ATR
    # ── Months ─────────────────────────────────────────────────────────────
    "MO": "MO", "MOS": "MO", "MON": "MO", "MONTH": "MO", "MONTHS": "MO",
    "MT": "MO",     # variant used in some workscopes
    # ── Days ───────────────────────────────────────────────────────────────
    "DY": "DY", "DAY": "DY", "DAYS": "DY", "CH": "DY",   # CH = calendar hours (24 h = 1 day)
    # ── Weeks ─────────────────────────────────────────────────────────────
    "WY": "WY", "WK": "WY", "WEEK": "WY", "WEEKS": "WY",
}

# Special non-numeric interval values — valid but not paired with a number.
SPECIAL_INTERVAL_VALUES = {"NR", "A", "WY", "OC", "SVC"}

# Units that cannot be compared directly against each other (require clarification).
# Key = raw abbreviation found in import, value = (canonical, question to ask user).
AMBIGUOUS_UNITS: dict[str, tuple[str, str]] = {
    "BH":  ("FH",  "Block Hours (BH) — treat as Flight Hours?"),
    "EFH": ("FH",  "Equivalent Flight Hours (EFH) — treat as Flight Hours?"),
    "LDG": ("LDG", "Landings (LDG) — note: NOT the same as Flight Cycles (FC)"),
    "LDGS":("LDG", "Landings (LDGS) — note: NOT the same as Flight Cycles (FC)"),
    "CH":  ("DY",  "Calendar Hours (CH) — treating 1 CH as 1 Day. Correct?"),
    "C":   ("C",   "Cycles (C) — ATR uses C for pressure cycles. Confirm this is cycles, not calendar?"),
}

# ── Unit detection helpers ────────────────────────────────────────────────────

# Regex to find "NUMBER UNIT" patterns inside a free-text string
_INTERVAL_TOKEN_RE = re.compile(
    r'\b(\d+(?:\.\d+)?)\s*([A-Z]{1,6})\b',
    re.IGNORECASE,
)


def detect_units_in_text(text: str) -> list[dict]:
    """Scan free text and return all interval-like tokens with their canonical unit.

    Returns a list of dicts:
      { "raw": "36 MO", "value": 36, "unit_raw": "MO",
        "unit_canonical": "MO", "ambiguous": False,
        "ambiguous_note": "" }

    Unknown units (not in UNIT_ALIASES) are flagged with unit_canonical=None.
    Ambiguous units (in AMBIGUOUS_UNITS) are flagged so callers can prompt the user.
    """
    results = []
    seen = set()
    for m in _INTERVAL_TOKEN_RE.finditer(text.upper()):
        val_str, unit_raw = m.group(1), m.group(2)
        key = (val_str, unit_raw)
        if key in seen:
            continue
        seen.add(key)
        canonical = UNIT_ALIASES.get(unit_raw)
        is_ambiguous = unit_raw in AMBIGUOUS_UNITS
        results.append({
            "raw": m.group(0),
            "value": float(val_str),
            "unit_raw": unit_raw,
            "unit_canonical": canonical,
            "known": canonical is not None,
            "ambiguous": is_ambiguous,
            "ambiguous_note": AMBIGUOUS_UNITS.get(unit_raw, ("", ""))[1],
        })
    return results


def scan_column_for_unknown_units(values: list[str]) -> list[dict]:
    """Scan a list of cell values (e.g. a workscope interval column) and return
    any unit abbreviations that are unknown or ambiguous.

    Returns a deduplicated list of warning dicts suitable for showing in the
    import mapping UI.
    """
    seen_units: set[str] = set()
    warnings: list[dict] = []
    for cell in values:
        if not cell:
            continue
        for tok in detect_units_in_text(cell):
            u = tok["unit_raw"]
            if u in seen_units:
                continue
            seen_units.add(u)
            if not tok["known"]:
                warnings.append({
                    "unit": u,
                    "example": tok["raw"],
                    "kind": "unknown",
                    "message": f"Unknown unit '{u}' — not in unit table. Please check.",
                })
            elif tok["ambiguous"]:
                warnings.append({
                    "unit": u,
                    "example": tok["raw"],
                    "kind": "ambiguous",
                    "message": tok["ambiguous_note"],
                })
    return warnings


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
