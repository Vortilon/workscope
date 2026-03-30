"""
OCR service — tiered PDF table extraction.

Tier 1 (free, always available):  pdfplumber + camelot
  - Native PDFs (text layer present): best quality, zero overhead.
  - camelot lattice/stream for structured tables.
  - Multi-page table stitching across page boundaries.

Tier 2 (free, requires tesseract-ocr system package):  Tesseract 5 + OpenCV
  - Scanned PDFs: deskew → denoise → threshold → OCR per page.
  - Returns per-cell confidence scores; low-confidence cells flagged.

Tier 3 (paid, requires Google Document AI credentials):  Google Document AI
  - Complex/poor-quality scans, mixed content, broken pagination.
  - Natively reconstructs multi-page tables.
  - Requires: GCP_PROJECT_ID, DOCAI_PROCESSOR_ID, DOCAI_LOCATION,
              GOOGLE_APPLICATION_CREDENTIALS (path to service-account JSON).

Usage
-----
    from app.services.ocr import extract_tables_from_pdf, OcrResult

    result: OcrResult = await extract_tables_from_pdf(path, prefer_tier=None)
    # result.tables  — list of dicts per row
    # result.tier    — "1-pdfplumber" | "1-camelot" | "2-tesseract" | "3-docai"
    # result.warnings — list of human-readable warning strings
    # result.low_confidence_cells — [(row_idx, col_name, value, confidence), ...]
"""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger("ocr")

# ── Result container ───────────────────────────────────────────────────────────

@dataclass
class OcrResult:
    tables: list[dict[str, Any]] = field(default_factory=list)
    """Each item is one data row: {column_name: cell_value, ...}"""

    raw_rows: list[list[str]] = field(default_factory=list)
    """Raw rows (list-of-lists) before column-name mapping — used by the mapping wizard."""

    header: list[str] = field(default_factory=list)
    """Detected header row."""

    tier: str = "unknown"
    warnings: list[str] = field(default_factory=list)
    low_confidence_cells: list[tuple[int, str, str, float]] = field(default_factory=list)
    """(row_index, column_name, cell_value, confidence 0-1)"""

    page_count: int = 0
    row_count: int = 0


# ── Tier detection ─────────────────────────────────────────────────────────────

def _pdf_has_text_layer(path: Path) -> bool:
    """Return True if the PDF has a selectable text layer (native PDF)."""
    try:
        import pdfplumber
        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages[:3]:
                text = page.extract_text() or ""
                if len(text.strip()) > 50:
                    return True
        return False
    except Exception:
        return False


def _camelot_available() -> bool:
    try:
        import camelot  # noqa: F401
        return True
    except ImportError:
        return False


def _tesseract_available() -> bool:
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def _docai_configured() -> bool:
    return bool(
        os.environ.get("GCP_PROJECT_ID")
        and os.environ.get("DOCAI_PROCESSOR_ID")
        and os.environ.get("DOCAI_LOCATION")
        and (
            os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
            or os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
        )
    )


# ── Tier 1a: pdfplumber (native PDF) ──────────────────────────────────────────

def _extract_tier1_pdfplumber(path: Path) -> OcrResult:
    """Extract tables from a native PDF using pdfplumber with multi-page stitching."""
    import pdfplumber

    result = OcrResult(tier="1-pdfplumber")
    all_rows: list[list[str]] = []
    header: list[str] | None = None
    pending_partial: list[str] | None = None  # last row of prev page if incomplete

    with pdfplumber.open(str(path)) as pdf:
        result.page_count = len(pdf.pages)
        for page_num, page in enumerate(pdf.pages):
            tbl = page.extract_table()
            if not tbl:
                continue

            rows = [[str(c or "").strip() for c in row] for row in tbl]

            # Detect header row (first page only, first non-empty row)
            if header is None:
                for i, row in enumerate(rows):
                    if any(c for c in row):
                        header = row
                        rows = rows[i + 1:]
                        break

            if not rows:
                continue

            # Multi-page stitch: if last row of previous page had trailing empty cells
            # and first row of this page has leading empty cells, merge them.
            if pending_partial is not None and rows:
                first = rows[0]
                # Heuristic: if first cell of current page is empty, it's a continuation
                if not first[0].strip():
                    merged = [
                        (pending_partial[i] + " " + first[i]).strip()
                        for i in range(min(len(pending_partial), len(first)))
                    ]
                    all_rows[-1] = merged
                    rows = rows[1:]
                pending_partial = None

            # Check if last row of this page might continue on next page
            if rows:
                last = rows[-1]
                empty_trailing = sum(1 for c in last if not c.strip())
                if empty_trailing >= len(last) // 2:
                    pending_partial = last

            all_rows.extend(rows)

    result.header = header or []
    result.raw_rows = all_rows
    result.row_count = len(all_rows)

    if not all_rows and not header:
        result.warnings.append("pdfplumber found no tables — PDF may be scanned (image-only).")

    return result


# ── Tier 1b: camelot (native PDF, better for complex grids) ───────────────────

def _extract_tier1_camelot(path: Path) -> OcrResult:
    """Extract tables using camelot — better for PDFs with explicit grid lines."""
    import camelot
    import pandas as pd

    result = OcrResult(tier="1-camelot")
    all_rows: list[list[str]] = []
    header: list[str] | None = None

    try:
        # Try lattice first (tables with visible grid lines)
        tables = camelot.read_pdf(str(path), pages="all", flavor="lattice")
        if not tables or tables.n == 0:
            # Fall back to stream (whitespace-separated columns)
            tables = camelot.read_pdf(str(path), pages="all", flavor="stream")

        result.page_count = tables.n

        for tbl in tables:
            df: pd.DataFrame = tbl.df
            if df.empty:
                continue

            rows = df.values.tolist()
            rows = [[str(c).strip() for c in row] for row in rows]

            if header is None and rows:
                header = rows[0]
                rows = rows[1:]

            # Flag low-accuracy cells (camelot provides per-cell accuracy via whitespace)
            acc = tbl.accuracy
            if acc < 80:
                result.warnings.append(
                    f"Table on page {tbl.page} has low extraction accuracy ({acc:.0f}%) — "
                    "verify output carefully."
                )

            all_rows.extend(rows)

    except Exception as exc:
        result.warnings.append(f"camelot extraction failed: {exc}")
        # Fall back to pdfplumber
        fallback = _extract_tier1_pdfplumber(path)
        fallback.warnings.insert(0, "camelot failed — fell back to pdfplumber.")
        return fallback

    result.header = header or []
    result.raw_rows = all_rows
    result.row_count = len(all_rows)
    return result


# ── Tier 2: Tesseract + OpenCV (scanned PDF) ──────────────────────────────────

def _preprocess_image(img_array):
    """Deskew, denoise, and binarise a numpy image array for OCR."""
    import cv2
    import numpy as np

    gray = cv2.cvtColor(img_array, cv2.COLOR_RGB2GRAY)

    # Deskew
    coords = np.column_stack(np.where(gray < 200))
    if len(coords) > 100:
        angle = cv2.minAreaRect(coords)[-1]
        if angle < -45:
            angle = 90 + angle
        if abs(angle) > 0.5:
            (h, w) = gray.shape
            center = (w // 2, h // 2)
            M = cv2.getRotationMatrix2D(center, angle, 1.0)
            gray = cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_CUBIC,
                                   borderMode=cv2.BORDER_REPLICATE)

    # Denoise
    gray = cv2.fastNlMeansDenoising(gray, h=10)

    # Adaptive threshold (better than global for uneven lighting)
    binary = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
    )
    return binary


def _extract_tier2_tesseract(path: Path) -> OcrResult:
    """Extract tables from a scanned PDF using Tesseract 5 + OpenCV pre-processing."""
    import numpy as np
    import pytesseract
    import pdf2image

    result = OcrResult(tier="2-tesseract")
    all_rows: list[list[str]] = []
    header: list[str] | None = None
    low_conf: list[tuple[int, str, str, float]] = []

    pages = pdf2image.convert_from_path(str(path), dpi=300)
    result.page_count = len(pages)

    CONF_THRESHOLD = 0.70

    for page_num, pil_page in enumerate(pages):
        img = np.array(pil_page)
        processed = _preprocess_image(img)

        # Use image_to_data for bounding-box + confidence output
        data = pytesseract.image_to_data(
            processed,
            config="--psm 6 -l eng",
            output_type=pytesseract.Output.DICT,
        )

        # Reconstruct rows by grouping words into lines using their top-y coordinate
        line_map: dict[int, list[tuple[int, str, float]]] = {}
        for i, word in enumerate(data["text"]):
            word = word.strip()
            if not word:
                continue
            conf = float(data["conf"][i]) / 100.0
            if conf < 0:
                continue
            line_key = data["top"][i] // 20  # group words within 20px vertically
            x = data["left"][i]
            line_map.setdefault(line_key, []).append((x, word, conf))

        for line_key in sorted(line_map.keys()):
            words = sorted(line_map[line_key], key=lambda t: t[0])
            row_text = " ".join(w for _, w, _ in words)
            # Split on 2+ spaces as column separators (crude but effective for tabular text)
            import re
            cols = [c.strip() for c in re.split(r" {2,}|\t", row_text) if c.strip()]
            if not cols:
                continue

            # Track low-confidence words
            for x, word, conf in words:
                if conf < CONF_THRESHOLD:
                    row_idx = len(all_rows)
                    col_name = cols[0] if cols else "?"
                    low_conf.append((row_idx, col_name, word, conf))

            if header is None and page_num == 0:
                header = cols
            else:
                all_rows.append(cols)

    result.header = header or []
    result.raw_rows = all_rows
    result.row_count = len(all_rows)
    result.low_confidence_cells = low_conf

    if low_conf:
        result.warnings.append(
            f"{len(low_conf)} cells have low OCR confidence (<70%) — "
            "highlighted in the preview for your review."
        )

    # Normalise row lengths to match header
    if result.header:
        n = len(result.header)
        result.raw_rows = [
            (row + [""] * n)[:n] for row in result.raw_rows
        ]

    return result


# ── Tier 3: Google Document AI ────────────────────────────────────────────────

def _extract_tier3_docai(path: Path) -> OcrResult:
    """Extract tables using Google Document AI (Document OCR processor)."""
    import json as _json

    result = OcrResult(tier="3-docai")

    project_id = os.environ["GCP_PROJECT_ID"]
    processor_id = os.environ["DOCAI_PROCESSOR_ID"]
    location = os.environ.get("DOCAI_LOCATION", "us")

    # Handle inline service account JSON (stored as env var string)
    sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if sa_json:
        import tempfile
        tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False)
        tmp.write(sa_json)
        tmp.flush()
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = tmp.name

    try:
        from google.cloud import documentai
        from google.api_core.client_options import ClientOptions

        opts = ClientOptions(api_endpoint=f"{location}-documentai.googleapis.com")
        client = documentai.DocumentProcessorServiceClient(client_options=opts)

        processor_name = client.processor_path(project_id, location, processor_id)

        with open(path, "rb") as f:
            raw_doc = f.read()

        doc_input = documentai.RawDocument(
            content=raw_doc,
            mime_type="application/pdf",
        )
        request_obj = documentai.ProcessRequest(
            name=processor_name,
            raw_document=doc_input,
        )
        response = client.process_document(request=request_obj)
        document = response.document

        result.page_count = len(document.pages)

        all_rows: list[list[str]] = []
        header: list[str] | None = None
        low_conf: list[tuple[int, str, str, float]] = []

        CONF_THRESHOLD = 0.80

        for page in document.pages:
            for table in page.tables:
                # Header rows
                for header_row in table.header_rows:
                    if header is None:
                        header = [
                            _docai_cell_text(cell, document)
                            for cell in header_row.cells
                        ]
                # Body rows
                for body_row in table.body_rows:
                    row = []
                    for ci, cell in enumerate(body_row.cells):
                        text = _docai_cell_text(cell, document)
                        conf = _docai_cell_confidence(cell)
                        row.append(text)
                        if conf < CONF_THRESHOLD:
                            col_name = (header[ci] if header and ci < len(header)
                                        else str(ci))
                            low_conf.append((len(all_rows), col_name, text, conf))
                    all_rows.append(row)

        result.header = header or []
        result.raw_rows = all_rows
        result.row_count = len(all_rows)
        result.low_confidence_cells = low_conf

        if low_conf:
            result.warnings.append(
                f"{len(low_conf)} cells have low Document AI confidence (<80%) — "
                "highlighted in the preview."
            )

    except Exception as exc:
        result.warnings.append(f"Google Document AI failed: {exc}")
        log.exception("Document AI error")

    return result


def _docai_cell_text(cell, document) -> str:
    """Extract plain text from a DocumentAI table cell."""
    text = ""
    for seg in cell.layout.text_anchor.text_segments:
        start = int(seg.start_index) if seg.start_index else 0
        end = int(seg.end_index) if seg.end_index else 0
        text += document.text[start:end]
    return text.strip()


def _docai_cell_confidence(cell) -> float:
    return float(cell.layout.confidence) if cell.layout.confidence else 1.0


# ── Main entry point ───────────────────────────────────────────────────────────

async def extract_tables_from_pdf(
    path: Path,
    prefer_tier: int | None = None,
    force_ocr: bool = False,
) -> OcrResult:
    """
    Extract tabular data from a PDF using the best available tier.

    Parameters
    ----------
    path        : Path to the PDF file.
    prefer_tier : Force a specific tier (1, 2, or 3). None = auto-detect.
    force_ocr   : If True, skip native-PDF detection and go straight to OCR.
    """
    loop = asyncio.get_event_loop()

    # Auto-detect best tier
    if prefer_tier is None:
        if not force_ocr and _pdf_has_text_layer(path):
            prefer_tier = 1
        elif _tesseract_available():
            prefer_tier = 2
        elif _docai_configured():
            prefer_tier = 3
        else:
            # Fall back to pdfplumber even on scanned (will warn)
            prefer_tier = 1

    if prefer_tier == 3:
        if not _docai_configured():
            log.warning("Tier 3 requested but Document AI not configured — falling back to tier 2/1")
            prefer_tier = 2 if _tesseract_available() else 1

    if prefer_tier == 2:
        if not _tesseract_available():
            log.warning("Tier 2 requested but Tesseract not available — falling back to tier 1")
            prefer_tier = 1

    log.info("PDF extraction: %s using tier %d", path.name, prefer_tier)

    if prefer_tier == 3:
        result = await loop.run_in_executor(None, _extract_tier3_docai, path)
    elif prefer_tier == 2:
        result = await loop.run_in_executor(None, _extract_tier2_tesseract, path)
    else:
        # Tier 1: try camelot first (better for grids), fall back to pdfplumber
        if _camelot_available():
            result = await loop.run_in_executor(None, _extract_tier1_camelot, path)
        else:
            result = await loop.run_in_executor(None, _extract_tier1_pdfplumber, path)

        # If tier 1 produced no rows and tesseract is available, escalate to tier 2
        if result.row_count == 0 and _tesseract_available():
            result.warnings.insert(0,
                "Native PDF extraction found no tables — retrying with Tesseract OCR.")
            result = await loop.run_in_executor(None, _extract_tier2_tesseract, path)

        # If still nothing and Document AI is configured, escalate to tier 3
        if result.row_count == 0 and _docai_configured():
            result.warnings.insert(0,
                "Tesseract found no tables — retrying with Google Document AI.")
            result = await loop.run_in_executor(None, _extract_tier3_docai, path)

    return result
