from __future__ import annotations

import hashlib
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def sha256_bytes(data: bytes) -> str:
    h = hashlib.sha256()
    h.update(data)
    return h.hexdigest()


def new_uuid() -> str:
    return str(uuid.uuid4())


def safe_filename(name: str) -> str:
    name = name.strip().replace("\x00", "")
    name = re.sub(r"[^\w.\- ()]+", "_", name)
    return name[:180] if len(name) > 180 else name


def normalize_document_key(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"[^a-z0-9 _\-./]+", "", s)
    return s[:256] if len(s) > 256 else s


def derive_ata_chapter(task_reference: str | None) -> tuple[str | None, bool]:
    if not task_reference:
        return None, True
    m = re.match(r"^(\d{2})\d{4}[-/]", task_reference.strip())
    if m:
        return m.group(1), True
    m2 = re.match(r"^(\d{2})\d{4}$", task_reference.strip())
    if m2:
        return m2.group(1), True
    return None, True


def classify_task_type(task_reference: str | None, service_interval: str | None) -> str:
    tr = (task_reference or "").strip()
    si = (service_interval or "").strip().upper()
    if tr.startswith("AD ") or si.startswith("AD "):
        return "AD"
    if "OPERATOR" in si or "OPERATOR" in tr:
        return "OPERATOR"
    if "HT" in si or "HARD TIME" in si:
        return "HARD_TIME"
    if re.match(r"^\d", tr):
        return "MPD"
    return "UNKNOWN"


def api_key_required() -> str:
    return os.getenv("AVIATION_DOCS_API_KEY", "").strip()


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def json_sanitize(obj: Any) -> Any:
    # Best-effort: ensure JSON serializable without altering meaning.
    if obj is None:
        return None
    if isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, dict):
        return {str(k): json_sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [json_sanitize(x) for x in obj]
    return str(obj)
