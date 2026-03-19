from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass
class PdfParseResult:
    header: dict[str, Any]
    sections: list[dict[str, Any]]
    parts_list: list[dict[str, Any]]
    parse_warnings: list[str]
    confidence: str
    totals: dict[str, Any]
    used_ocr: bool


SECTION_MAP = {
    "SCHEDULED MAINTENANCE AIRCRAFT": "AIRCRAFT_TASKS",
    "SCHEDULED MAINTENANCE COMPONENTS": "COMPONENT_TASKS",
    "SCHEDULED MAINTENANCE DIRECTIVE": "DIRECTIVES",
    "NECESSARY COMPONENTS": "PARTS",
}

# Task reference patterns (MPD-style and ZL-... operator tasks)
TASK_REF_RE = re.compile(
    r"\b(?:\d{6}-\d{2}-\d(?:-[A-Z0-9]+)?|ZL-\d{3}-\d{2}-\d(?:-[A-Z0-9]+)?)\b",
    re.IGNORECASE,
)


def _clean(s: str) -> str:
    s = (s or "").replace("\x00", "").strip()
    s = re.sub(r"\s+", " ", s)
    return s


def _is_page_separator(line: str) -> bool:
    return bool(re.match(r"^--\s*\d+\s+of\s+\d+\s*--$", line.strip(), re.IGNORECASE))


def _extract_header_fields(first_page_text: str) -> dict[str, Any]:
    t = first_page_text
    header: dict[str, Any] = {"raw_fields": {}}
    # Most reliable fields in SOMA footer/header area
    m = re.search(r"Aircraft Type:\s*([A-Z0-9\-]+)", t)
    if m:
        header["aircraft_type"] = _clean(m.group(1))
    m = re.search(r"Registration:\s*([A-Z0-9\-]+)", t)
    if m:
        header["registration"] = _clean(m.group(1))
    m = re.search(r"Serial No\.\s*:\s*0*([0-9]+)", t)
    if m:
        header["msn"] = _clean(m.group(1))
    m = re.search(r"Operator:\s*([A-Z0-9 &\-]+)", t)
    if m:
        header["operator"] = _clean(m.group(1))
    m = re.search(r"Approval:\s*([A-Z0-9\-]+)", t)
    if m:
        header["approval_number"] = _clean(m.group(1))
    m = re.search(r"Work Pack No\.\s*:\s*(.+)", t)
    if m:
        header["check_type"] = _clean(m.group(1))
    m = re.search(r"Work Pack:\s*(.+)", t)
    if m and "check_type" not in header:
        header["check_type"] = _clean(m.group(1))
    m = re.search(r"\bWO N°:\s*([A-Z0-9]+)\b", t)
    if m:
        header["work_order_number"] = _clean(m.group(1))
    m = re.search(r"Start Date:\s*([0-9]{2}-[A-Za-z]{3}-[0-9]{4})", t)
    if m:
        header["start_date"] = m.group(1)
    # Engines often appear as two P/Ns + two S/Ns in header strip; capture best-effort
    # Keep as raw_fields if not confidently found.
    return header


def _group_chars_to_lines(chars: list[dict[str, Any]], y_tol: float = 2.0) -> list[list[dict[str, Any]]]:
    # Group characters by their "top" coordinate.
    chars_sorted = sorted(chars, key=lambda c: (c.get("top", 0.0), c.get("x0", 0.0)))
    lines: list[list[dict[str, Any]]] = []
    for ch in chars_sorted:
        if not lines:
            lines.append([ch])
            continue
        if abs(ch.get("top", 0.0) - lines[-1][0].get("top", 0.0)) <= y_tol:
            lines[-1].append(ch)
        else:
            lines.append([ch])
    return lines


def _line_text(line_chars: list[dict[str, Any]]) -> str:
    # Reconstruct text from characters using x gaps.
    line_chars = sorted(line_chars, key=lambda c: c.get("x0", 0.0))
    out = []
    prev_x1 = None
    for ch in line_chars:
        x0 = float(ch.get("x0", 0.0))
        x1 = float(ch.get("x1", x0))
        txt = ch.get("text", "")
        if prev_x1 is not None and x0 - prev_x1 > 1.6:
            out.append(" ")
        out.append(txt)
        prev_x1 = x1
    return _clean("".join(out))


def _split_line_by_columns(line_chars: list[dict[str, Any]], x_breaks: list[float]) -> list[str]:
    # x_breaks are increasing boundaries between columns (exclusive).
    buckets: list[list[dict[str, Any]]] = [[] for _ in range(len(x_breaks) + 1)]
    for ch in line_chars:
        x0 = float(ch.get("x0", 0.0))
        idx = 0
        while idx < len(x_breaks) and x0 >= x_breaks[idx]:
            idx += 1
        buckets[idx].append(ch)
    return [_line_text(b) if b else "" for b in buckets]


def _words_with_positions(line_chars: list[dict[str, Any]]) -> list[dict[str, float | str]]:
    chs = sorted(line_chars, key=lambda c: float(c.get("x0", 0.0)))
    words: list[dict[str, float | str]] = []
    buf: list[dict[str, Any]] = []
    prev_x1 = None
    for ch in chs:
        t = ch.get("text", "")
        if not t or t.strip() == "":
            continue
        x0 = float(ch.get("x0", 0.0))
        x1 = float(ch.get("x1", x0))
        if buf and prev_x1 is not None and x0 - prev_x1 > 2.2:
            words.append(
                {
                    "text": "".join(x["text"] for x in buf),
                    "x0": float(buf[0].get("x0", 0.0)),
                    "x1": float(buf[-1].get("x1", buf[-1].get("x0", 0.0))),
                }
            )
            buf = []
        buf.append(ch)
        prev_x1 = x1
    if buf:
        words.append(
            {
                "text": "".join(x["text"] for x in buf),
                "x0": float(buf[0].get("x0", 0.0)),
                "x1": float(buf[-1].get("x1", buf[-1].get("x0", 0.0))),
            }
        )
    return words


def _infer_task_table_breaks(lines: list[list[dict[str, Any]]]) -> list[float] | None:
    # Infer breakpoints for Service | TaskRef | Description based on observed word x positions.
    task_xs: list[float] = []
    desc_xs: list[float] = []
    task_ref_re = re.compile(r"^(?:\d{6}-\d{2}-\d-(?:[A-Z0-9]+)?|ZL-\d{3}-\d{2}-\d(?:-[A-Z0-9]+)?)$", re.IGNORECASE)
    for line_chars in lines[:250]:
        words = _words_with_positions(line_chars)
        for i, w in enumerate(words):
            txt = str(w["text"]).strip()
            if task_ref_re.match(txt):
                task_xs.append(float(w["x0"]))
                # first word after taskref is usually description start
                if i + 1 < len(words):
                    nxt = str(words[i + 1]["text"]).strip()
                    if nxt:
                        desc_xs.append(float(words[i + 1]["x0"]))
                break
    if not task_xs:
        return None
    task_x = sorted(task_xs)[len(task_xs) // 2]
    desc_x = sorted(desc_xs)[len(desc_xs) // 2] if desc_xs else (task_x + 90.0)
    # Breaks slightly before starts to avoid splitting digits.
    return [max(task_x - 2.0, 30.0), max(desc_x - 2.0, task_x + 10.0)]


def _detect_column_breaks_from_header(chars: list[dict[str, Any]]) -> list[float] | None:
    # Build word tokens with x0 and x1.
    chs = sorted(chars, key=lambda c: float(c.get("x0", 0.0)))
    words: list[dict[str, Any]] = []
    buf = []
    prev_x1 = None
    for ch in chs:
        t = ch.get("text", "")
        if not t or not re.match(r"[A-Za-z0-9/°]+", t):
            continue
        x0 = float(ch.get("x0", 0.0))
        x1 = float(ch.get("x1", x0))
        if buf and prev_x1 is not None and x0 - prev_x1 > 2.2:
            words.append(
                {
                    "text": "".join(x["text"] for x in buf),
                    "x0": float(buf[0].get("x0", 0.0)),
                    "x1": float(buf[-1].get("x1", buf[-1].get("x0", 0.0))),
                }
            )
            buf = []
        buf.append(ch)
        prev_x1 = x1
    if buf:
        words.append(
            {
                "text": "".join(x["text"] for x in buf),
                "x0": float(buf[0].get("x0", 0.0)),
                "x1": float(buf[-1].get("x1", buf[-1].get("x0", 0.0))),
            }
        )

    joined = " ".join(w["text"] for w in words).upper()
    if "SERVICE" not in joined or "DESCRIPTION" not in joined:
        return None

    # Find indices of key headers and compute breaks using previous word end (x1) and current start (x0).
    def find_idx(word: str) -> int | None:
        wu = word.upper()
        for i, w in enumerate(words):
            if w["text"].upper() == wu:
                return i
        return None

    idx_task = find_idx("Task")
    idx_desc = find_idx("Description")
    idx_mh = find_idx("MH")

    if idx_task is None or idx_desc is None:
        return None

    def midpoint(prev_i: int, cur_i: int) -> float:
        prev_x1 = float(words[prev_i]["x1"])
        cur_x0 = float(words[cur_i]["x0"])
        return (prev_x1 + cur_x0) / 2.0

    breaks: list[float] = []
    if idx_task > 0:
        breaks.append(midpoint(idx_task - 1, idx_task))
    else:
        breaks.append(float(words[idx_task]["x0"]) - 1.0)

    if idx_desc > 0:
        breaks.append(midpoint(idx_desc - 1, idx_desc))
    else:
        breaks.append(float(words[idx_desc]["x0"]) - 1.0)

    if idx_mh is not None and idx_mh > 0:
        breaks.append(midpoint(idx_mh - 1, idx_mh))

    return sorted(set(breaks))


def parse_pdf_soma(path: Path) -> PdfParseResult:
    import pdfplumber

    warnings: list[str] = []
    sections: dict[str, list[dict[str, Any]]] = {}
    parts_list: list[dict[str, Any]] = []
    used_ocr = False

    with pdfplumber.open(str(path)) as pdf:
        if not pdf.pages:
            return PdfParseResult(
                header={"raw_fields": {}},
                sections=[],
                parts_list=[],
                parse_warnings=["PDF: empty document"],
                confidence="low",
                totals={"total_task_rows_in_document": 0, "total_rows_extracted": 0, "extraction_match": True, "total_mh_sum": 0.0, "sections_found": []},
                used_ocr=False,
            )

        first_text = pdf.pages[0].extract_text() or ""
        if first_text.strip() == "":
            used_ocr = True
            return PdfParseResult(
                header={"raw_fields": {}},
                sections=[],
                parts_list=[],
                parse_warnings=["PDF: no text layer detected; OCR required but not executed in this run"],
                confidence="low",
                totals={"total_task_rows_in_document": 0, "total_rows_extracted": 0, "extraction_match": False, "total_mh_sum": 0.0, "sections_found": []},
                used_ocr=True,
            )

        header = _extract_header_fields(first_text)
        header.setdefault("source_system", "SOMA Aeronautical Software")

        current_section: str | None = None
        current_section_type: str | None = None
        x_breaks: list[float] | None = None

        row_starts_detected = 0
        extracted_rows = 0
        reconstructed_task_refs = 0

        # Per-section row state (for wrapped multi-line rows)
        pending: dict[str, Any] | None = None

        def flush_pending():
            nonlocal pending, extracted_rows
            if not pending:
                return
            sec = pending.pop("_section_type", "UNKNOWN")
            sections.setdefault(sec, []).append(pending)
            extracted_rows += 1
            pending = None

        for page_index, page in enumerate(pdf.pages):
            chars = page.chars or []
            lines = _group_chars_to_lines(chars, y_tol=2.0)

            # Find column breaks per page based on header row chars when possible.
            if x_breaks is None:
                for line_chars in lines[:25]:
                    line = _line_text(line_chars)
                    if "SERVICE" in line.upper() and "DESCRIPTION" in line.upper():
                        b = _detect_column_breaks_from_header(line_chars)
                        if b:
                            x_breaks = b
                            break
            # Fallback: infer task-table breaks from observed task reference positions.
            if x_breaks is None:
                b2 = _infer_task_table_breaks(lines)
                if b2:
                    x_breaks = b2

            for line_chars in lines:
                raw_line = _line_text(line_chars)
                if not raw_line:
                    continue
                if _is_page_separator(raw_line):
                    continue
                upper = raw_line.upper()
                if "THIS DOCUMENT HAS BEEN GENERATED BY SOMA" in upper:
                    continue
                if upper.startswith("WORK ORDER") or upper.startswith("TALLY"):
                    continue
                if upper.startswith("AIRBUS ") and "ARUBA" in upper:
                    continue
                if upper.startswith("SCHEDULED MAINTENANCE") or upper.startswith("NECESSARY COMPONENTS"):
                    for key, mapped in SECTION_MAP.items():
                        if key in upper:
                            flush_pending()
                            current_section = key
                            current_section_type = mapped
                            pending = None
                            break
                    continue
                # skip repeated column header row
                if "SERVICE" in upper and "TASK" in upper and "DESCRIPTION" in upper:
                    continue

                if current_section_type is None:
                    continue

                cols = _split_line_by_columns(line_chars, x_breaks) if x_breaks else [raw_line]

                if current_section_type in {"AIRCRAFT_TASKS", "DIRECTIVES"}:
                    # Expect 6 columns, but tolerate variance.
                    service = cols[0] if len(cols) > 0 else ""
                    taskref = cols[1] if len(cols) > 1 else ""
                    desc = cols[2] if len(cols) > 2 else ""
                    mh = cols[3] if len(cols) > 3 else ""

                    # Prefer task reference detected anywhere in the raw line (exact token),
                    # so we are robust to small column-boundary shifts.
                    m_tr = TASK_REF_RE.search(raw_line)
                    if m_tr:
                        taskref = m_tr.group(0)

                    # Detect start of new row: service interval pattern or AD pattern.
                    is_start = bool(re.match(r"^[A-Z0-9]{3,5}\s*-\s*(?:\d+|ALI|OOP)\b", service)) or raw_line.upper().startswith("AD ")
                    if is_start:
                        flush_pending()
                        row_starts_detected += 1
                        pending = {
                            "_section_type": current_section_type,
                            "line_number": extracted_rows + 1,
                            "service_interval": service or None,
                            "task_reference": taskref or None,
                            "description": desc or None,
                            "man_hours": None,
                            "status": None,
                            "raw_line": raw_line,
                            "task_type": None,
                            "ad_reference": None,
                            "component_pn": None,
                            "component_sn": None,
                            "component_position": None,
                            "component_description": None,
                            "extra_fields": {},
                        }
                        # MH parsing: keep null if blank/zero-like not reliably numeric
                        mh_clean = mh.strip()
                        if mh_clean and re.match(r"^[0-9]+(\.[0-9]+)?$", mh_clean):
                            pending["man_hours"] = float(mh_clean)
                        continue

                    # Continuation line: may be split service/taskref/desc
                    if pending:
                        # If task ref split like "321113-04-1-" then "R" next line (cols[1] holds suffix)
                        c1 = (cols[1] if len(cols) > 1 else "").strip()
                        suffix = c1 or raw_line.strip()
                        if pending.get("task_reference") and str(pending["task_reference"]).endswith("-") and suffix and len(suffix) <= 3:
                            pending["task_reference"] = str(pending["task_reference"]) + suffix
                            reconstructed_task_refs += 1
                            pending["raw_line"] = (pending.get("raw_line") or "") + " | " + raw_line
                            continue
                        # Service interval split e.g. "A320 - 6" + "Months"
                        if pending.get("service_interval") and pending["service_interval"].endswith((" - 6", " - 12", " - 24", " - 36", " - 48", " - 72")) and cols[0].strip():
                            pending["service_interval"] = _clean(f"{pending['service_interval']} {cols[0]}")
                            pending["raw_line"] = (pending.get("raw_line") or "") + " | " + raw_line
                            continue
                        # Description wrap
                        col2 = cols[2] if len(cols) > 2 else ""
                        if col2.strip() or raw_line.strip():
                            d = col2.strip() if col2.strip() else raw_line.strip()
                            if d:
                                pending["description"] = _clean(((pending.get("description") or "") + " " + d).strip())
                                pending["raw_line"] = (pending.get("raw_line") or "") + " | " + raw_line
                                continue
                    continue

                if current_section_type == "COMPONENT_TASKS":
                    service = cols[0] if len(cols) > 0 else ""
                    taskref = cols[1] if len(cols) > 1 else ""
                    desc = cols[2] if len(cols) > 2 else ""
                    pn = cols[6] if len(cols) > 6 else ""
                    sn = cols[7] if len(cols) > 7 else ""
                    pos = cols[8] if len(cols) > 8 else ""
                    comp_desc = cols[9] if len(cols) > 9 else ""

                    m_tr = TASK_REF_RE.search(raw_line)
                    if m_tr:
                        taskref = m_tr.group(0)

                    is_start = bool(re.match(r"^[A-Z0-9]{3,5}\s*-\s*(?:\d+|ALI|OOP)\b", service)) or "OPERATOR" in service.upper() or "HARD TIME" in service.upper()
                    if is_start:
                        flush_pending()
                        row_starts_detected += 1
                        pending = {
                            "_section_type": current_section_type,
                            "line_number": extracted_rows + 1,
                            "service_interval": service or None,
                            "task_reference": taskref or None,
                            "description": desc or None,
                            "man_hours": None,
                            "status": None,
                            "raw_line": raw_line,
                            "task_type": None,
                            "ad_reference": None,
                            "component_pn": pn or None,
                            "component_sn": sn or None,
                            "component_position": pos or None,
                            "component_description": comp_desc or None,
                            "extra_fields": {},
                        }
                        continue

                    if pending:
                        c1 = (cols[1] if len(cols) > 1 else "").strip()
                        suffix = c1 or raw_line.strip()
                        if pending.get("task_reference") and str(pending["task_reference"]).endswith("-") and suffix and len(suffix) <= 3:
                            pending["task_reference"] = str(pending["task_reference"]) + suffix
                            reconstructed_task_refs += 1
                            pending["raw_line"] = (pending.get("raw_line") or "") + " | " + raw_line
                            continue
                        d = cols[2].strip() if len(cols) > 2 else raw_line.strip()
                        if d:
                            pending["description"] = _clean(((pending.get("description") or "") + " " + d).strip())
                            pending["raw_line"] = (pending.get("raw_line") or "") + " | " + raw_line
                            # if later columns appear on continuation, capture if empty
                            if not pending.get("component_pn") and pn.strip():
                                pending["component_pn"] = pn.strip()
                            if not pending.get("component_sn") and sn.strip():
                                pending["component_sn"] = sn.strip()
                            if not pending.get("component_position") and pos.strip():
                                pending["component_position"] = pos.strip()
                            if not pending.get("component_description") and comp_desc.strip():
                                pending["component_description"] = comp_desc.strip()
                            continue
                    continue

                if current_section_type == "PARTS":
                    # Parts lines often come as: task_reference part_number description unit qty type (order varies)
                    if raw_line.upper().startswith("P/N"):
                        continue
                    m = re.match(r"^(\S+)\s+(.+?)\s+(\d+(?:\.\d+)?)\s+(\S+)\s+(Expendable|Rotable|Tools|Equipment)\s*$", raw_line, re.IGNORECASE)
                    if m:
                        parts_list.append(
                            {
                                "task_reference": _clean(m.group(1)),
                                "part_number": _clean(m.group(2)),
                                "description": None,
                                "part_type": m.group(5).title(),
                                "unit": _clean(m.group(4)),
                                "quantity": float(m.group(3)),
                                "raw_line": raw_line,
                                "extra_fields": {},
                            }
                        )
                    continue

        flush_pending()

    # Normalize tasks: derive ATA, classify type, label derived.
    all_tasks: list[dict[str, Any]] = []
    for sec, tasks in sections.items():
        for t in tasks:
            tr = t.get("task_reference")
            ata = None
            if tr:
                m = re.match(r"^(\d{2})\d{4}[-/]", str(tr).strip())
                if m:
                    ata = m.group(1)
            t["ata_chapter"] = ata
            t["ata_derived"] = True
            t["task_type"] = "AD" if (t.get("service_interval") or "").upper().startswith("AD ") else ("MPD" if (tr and re.match(r"^\d", str(tr))) else "UNKNOWN")
            all_tasks.append(t)

    extracted = len(all_tasks)
    expected = row_starts_detected
    extraction_match = (expected == extracted) if expected > 0 else True
    if expected > 0 and expected != extracted:
        warnings.append(f"Row count mismatch: detected {expected} row starts, extracted {extracted} rows")

    if reconstructed_task_refs > 0:
        ratio = reconstructed_task_refs / max(extracted, 1)
        warnings.append(f"Reconstructed task references from split lines: {reconstructed_task_refs} ({ratio:.1%})")

    confidence = "high"
    if used_ocr:
        confidence = "low"
    elif reconstructed_task_refs / max(extracted, 1) > 0.02:
        confidence = "low"
    elif not extraction_match:
        confidence = "low"

    totals = {
        "total_task_rows_in_document": expected if expected > 0 else extracted,
        "total_rows_extracted": extracted,
        "extraction_match": extraction_match,
        "total_mh_sum": float(sum(t["man_hours"] for t in all_tasks if isinstance(t.get("man_hours"), (int, float)))),
        "sections_found": list(sections.keys()),
    }

    section_objs = [{"section_type": sec, "task_count": len(tasks), "tasks": tasks} for sec, tasks in sections.items()]
    return PdfParseResult(
        header=header,
        sections=section_objs,
        parts_list=parts_list,
        parse_warnings=warnings,
        confidence=confidence,
        totals=totals,
        used_ocr=used_ocr,
    )

