# Scopewrath (MPD-Workscope) — Complete Handover Document

This document is for the receiving AI agent / developer. It is exhaustive so development can continue without prior context.

**Repository:** Git remote may be `https://github.com/Vortilon/workscope.git` (project name mpd-workscope / Scopewrath). Server deploy path: `/opt/mpd-workscope`.

---

## 1. Project summary

### What Scopewrath does

**Scopewrath** (internal/codebase name: **mpd-workscope**) is a production-ready MVP for **aircraft maintenance workscope validation** against manufacturer **MPDs (Maintenance Planning Documents)**. It:

- **Ingests MPDs** (Excel): upload by manufacturer/model/revision; multi-sheet wizard with column mapping; tasks stored with raw + normalized intervals and applicability.
- **Manages projects** (one per aircraft MSN): link to an MPD dataset, upload workscope (Excel or, via separate pipeline, PDF/Excel aviation docs).
- **Parses workscopes**: Excel → heuristic column detection → `ParsedWorkscopeRow`; **aviation document pipeline** (PDF SOMA-style, Excel generic) → canonical JSON + `aviation_documents` / `aviation_document_tasks` / `aviation_document_parts` for use by external systems (e.g. Perkins).
- **Matches workscope tasks to MPD tasks**: deterministic exact match, then normalized match; no AI in matching today. Optional AI-assisted **structure detection** (column mapping) exists but uses sanitized payloads only.
- **Applicability/effectivity**: YES | NO | TBC per match; evidence upload (Phase 2) and condition resolution are stubbed.
- **Reporting**: Clickable counts (total, matched, effective, TBC, unmatched) with task lists.
- **Data privacy**: No proprietary/confidential data sent to external AI; sanitization layer and audit logging.

### Current state

- **Working**: MPD import wizard (upload → sheets → mapping → import), project CRUD, workscope Excel upload and parse, exact + normalized matching, report summary and match list, web UI (login, MPD library, project list/detail, report page), read-only MPD API for external callers, **aviation document ingestion** (PDF SOMA + Excel generic, revisioning, persist, query/validate), user admin (CRUD, password, toggle active).
- **Partially working / needs refinement**: Aviation PDF extractor (SOMA): task references and row counts mostly correct; some split task IDs (e.g. `321113-04-1-R`) may still be missing trailing suffix in edge cases; column boundaries vary by PDF layout. Excel aviation parser: generic fuzzy column mapping; merged cells and multi-sheet handled.
- **Not implemented / stubs**: PDF workscope in the **project** flow (only Excel); OCR for scanned PDFs; AI-assisted matching (only structure suggestion is wired); evidence extraction from uploaded files (Phase 2); pattern-based and AI-assisted match layers in the matching engine; applicability resolution UI and evidence-driven evaluation; “rule-request” and full Perkins integration endpoints.

### What is not working (known gaps)

- **Session secret** is hardcoded in `main.py` (`noteify-mpd-session-secret`); TODO to move to env in production.
- **Aviation docs API**: If `AVIATION_DOCS_API_KEY` is set, `X-API-Key` is required; if unset, no auth (intended for internal network). No `.env.example` entry for `AVIATION_DOCS_API_KEY` yet.
- **OpenAI provider**: Stub only; returns empty string / empty dict.
- **Evidence upload**: Stores file and creates `ModificationEvidenceFile` with `validation_status="pending"`; no extraction or applicability mapping yet (Phase 2).
- **Report placeholders**: `effective_not_in_workscope`, `extra_in_workscope_not_in_mpd`, `not_required_for_selected_checks` are always 0 (Phase 2).

---

## 2. Repository structure

All folders and key files with a one-line description.

```
mpd-workscope/
├── main.py                    # FastAPI app entry; lifespan, static, session, router includes
├── README.md                  # Project overview, setup, Docker, env, external API summary
├── requirements.txt           # Python deps: FastAPI, uvicorn, SQLAlchemy, openpyxl, pdfplumber, rapidfuzz, etc.
├── Dockerfile                 # Python 3.12-slim; COPY app; entrypoint runs migrations + uvicorn
├── docker-compose.yml         # Single service "app", volume ./data, port 8084, env_file .env
├── entrypoint.sh              # alembic upgrade head; uvicorn on PORT (default 8084)
├── alembic.ini                # Alembic config; sqlalchemy.url overridden in env.py
├── .env.example               # PORT, DATABASE_URL, AI_PROVIDER, GROK_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY
├── .gitignore                 # Standard Python/IDE ignores
│
├── alembic/
│   ├── env.py                 # Uses SYNC_DATABASE_URL, imports app.models for metadata
│   ├── script.py.mako         # Migration template
│   └── versions/
│       ├── 2c6ae3cbcd42_initial_schema.py   # audit_log, mpd_*, projects, project_*, parsed_workscope_*, workscope_*
│       ├── 3a1b2c3d4e5f_add_users_table.py  # users
│       └── 8f1a9c2d1b07_add_aviation_document_tables.py  # aviation_documents, aviation_document_tasks, aviation_document_parts
│
├── app/
│   ├── __init__.py
│   ├── config.py              # BASE_DIR, UPLOAD_DIR, MPD_STORAGE, REPORT_DIR, IMPORT_TEMP_DIR, DATABASE_URL, SYNC_DATABASE_URL, AI keys, PORT
│   ├── database.py            # Async SQLAlchemy engine + AsyncSessionLocal; get_db
│   ├── auth.py                # verify_password, hash_password (bcrypt), ensure_admin_seed
│   │
│   ├── models/
│   │   ├── __init__.py        # Exports all models for Alembic
│   │   ├── mpd.py             # MPDDataset, MPDTask
│   │   ├── project.py         # Project, ProjectCheck, ProjectFile, ApplicabilityCondition, ProjectConditionAnswer, ModificationEvidenceFile
│   │   ├── workscope.py       # ParsedWorkscopeRow, WorkscopeMatchCandidate, WorkscopeMatch
│   │   ├── aviation_document.py  # AviationDocument, AviationDocumentTask, AviationDocumentPart
│   │   ├── user.py            # User
│   │   ├── audit.py           # AuditLog
│   │   └── report.py          # ProjectReport
│   │
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── web.py             # HTML routes: /, /mpd, /mpd/{id}, /projects, /projects/new, /projects/{id}, /report/{id}; login gating
│   │   ├── api.py             # JSON API: MPD list/upload, datasets/tasks, projects CRUD, workscope upload, match, report, matches
│   │   ├── aviation_docs.py   # Aviation docs API: upload, documents, documents/{id}, tasks, validate, query (X-API-Key if set)
│   │   ├── auth.py            # GET/POST /login, GET /logout
│   │   ├── admin.py           # Admin: /admin/users CRUD, password, toggle-active, delete
│   │   ├── evidence.py        # POST /api/projects/{id}/evidence/upload (Phase 2 stub)
│   │   └── mpd_import_routes.py  # MPD import wizard: /mpd/import (upload, sheets, mapping, run, result)
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── mpd_import.py      # create_dataset, get_workbook_sheets, get_sheet_headers, import_mpd_excel_with_mapping, set_dataset_done
│   │   ├── workscope_import.py # detect_file_type, heuristic column mapping, parse_workscope_excel, get_candidate_mapping
│   │   ├── matching.py        # exact_match, normalized_match, run_initial_matching (no pattern/AI layers)
│   │   ├── reporting.py       # get_report_summary, get_match_list
│   │   ├── applicability.py  # evaluate_task_applicability, set_match_applicability
│   │   ├── normalize.py       # normalize_interval_raw, normalize_applicability_tokens
│   │   └── aviation_docs/
│   │       ├── utils.py       # uuid, sha256, safe_filename, document_key, derive_ata_chapter, classify_task_type, api_key_required
│   │       ├── parser_excel.py # Generic Excel parse: merged cells, fuzzy column map, sections/parts_list
│   │       ├── parser_pdf_soma.py # SOMA PDF: pdfplumber chars, column breaks, section detection, row reconstruction, ATA derivation
│   │       └── service.py     # ingest_document, list_documents, get_document_json, query_tasks; revisioning (is_latest)
│   │
│   ├── templates/             # Jinja2 HTML (base, login, home, mpd_*, projects, project_*, report, admin/*, mpd_import/*)
│   └── static/                # CSS, img (e.g. DAE logo placeholder)
│
├── ai/
│   ├── __init__.py
│   ├── memory.py              # RuleMemory, ProjectMemory (in-memory), PromptContextBuilder
│   ├── sanitizer.py           # sanitize_* for AI; log_sanitized_sent (audit file)
│   ├── redaction.py           # redact_string, redact_dict, redact_for_ai (serial/reg patterns)
│   ├── prompt_templates.py    # STRUCTURE_DETECTION_SYSTEM, MATCHING_HINT_SYSTEM
│   └── providers/
│       ├── __init__.py
│       ├── base.py            # BaseAIProvider (complete, structure_suggestion)
│       ├── grok.py            # GrokProvider (x.ai API)
│       └── openai.py         # OpenAIProvider (stub)
│
├── docs/
│   ├── EXTERNAL_DB_READONLY.md  # DB paths, MPD tables, read-only API for external clients
│   ├── SERVER_SETUP.md          # DNS, install, Nginx, certbot, ports, SSH, deploy
│   └── HANDOVER.md              # This file
│
├── scripts/
│   ├── setup-nginx.sh         # Creates Nginx site for mpd.noteify.us → 8084
│   └── deploy.sh             # git pull; docker compose up -d --build
│
├── data/                     # Runtime: uploads, mpd_workscope.db, reports, import_temp, aviation_docs (created by app)
├── samples/                  # .gitkeep
├── fixtures/                 # .gitkeep
├── backend/                  # __init__.py only (placeholder)
└── helloworld / mpd-workscope/helloworld  # Unused/legacy
```

---

## 3. All API endpoints

Format: **Method, path, what it does, request/response, status (complete / stub)**.

### Health and info

| Method | Path | Description | Request | Response | Status |
|--------|------|-------------|---------|----------|--------|
| GET | `/health` | Liveness | — | `{"status":"ok","app":"mpd-workscope"}` | Complete |
| GET | `/api` | API info | — | `{"message":"...", "docs":"/docs"}` | Complete |

### Auth (no prefix)

| Method | Path | Description | Request | Response | Status |
|--------|------|-------------|---------|----------|--------|
| GET | `/login` | Login page (HTML) | — | HTML | Complete |
| POST | `/login` | Login submit | Form: username, password | Redirect or HTML with error | Complete |
| GET | `/logout` | Logout | — | Redirect to /login | Complete |

### Web UI (HTML, login-required)

| Method | Path | Description | Status |
|--------|------|-------------|--------|
| GET | `/` | Home | Complete |
| GET | `/mpd` | MPD library list | Complete |
| GET | `/mpd/{dataset_id}` | MPD detail + tasks (limit 200) | Complete |
| GET | `/projects` | Project list | Complete |
| GET | `/projects/new` | New project form | Complete |
| GET | `/projects/{project_id}` | Project detail | Complete |
| GET | `/report/{project_id}` | Report page (summary + JSON) | Complete |
| GET | `/mpd/import` | MPD import step 1 (upload) | Complete |
| POST | `/mpd/import/upload` | MPD import upload file | Form: manufacturer, model, revision, file | Complete |
| GET | `/mpd/import/sheets` | MPD import step 2 (select sheets) | Complete |
| POST | `/mpd/import/sheets` | MPD import submit sheets | Form: selected[] | Complete |
| GET | `/mpd/import/mapping` | MPD import step 3 (column mapping) | Complete |
| POST | `/mpd/import/run` | MPD import run (creates dataset, imports, redirect to result) | Form: mapping keys | Complete |
| GET | `/mpd/import/result` | MPD import result page | Complete |
| GET | `/admin/users` | User list (admin) | Complete |
| GET | `/admin/users/new` | New user form | Complete |
| POST | `/admin/users` | Create user | Form: username, first_name, last_name, email, password, role | Complete |
| GET | `/admin/users/{user_id}/edit` | Edit user form | Complete |
| POST | `/admin/users/{user_id}` | Update user | Form: username, first_name, last_name, email, role | Complete |
| GET | `/admin/users/{user_id}/password` | Password form | Complete |
| POST | `/admin/users/{user_id}/password` | Set password | Form: password | Complete |
| POST | `/admin/users/{user_id}/toggle-active` | Toggle user active | — | Complete |
| POST | `/admin/users/{user_id}/delete` | Delete user | — | Complete |

### JSON API (`/api`)

| Method | Path | Description | Request | Response | Status |
|--------|------|-------------|---------|----------|--------|
| GET | `/api/mpd` | List MPD datasets (short) | — | `[{id, manufacturer, model, revision, parsed_status}]` | Complete |
| GET | `/api/mpd/datasets` | List MPD datasets (full) | — | `[{id, manufacturer, model, revision, parsed_status, source_file, created_at}]` | Complete |
| GET | `/api/mpd/datasets/{dataset_id}/tasks` | List MPD tasks; optional `section`, `limit`, `offset` | Query: section, limit (default 100, max 1000), offset | Array of task objects | Complete |
| POST | `/api/mpd/upload` | Upload MPD Excel (simple; no wizard) | Form: manufacturer, model, revision, version?, file | `{id, task_count}` | Complete |
| POST | `/api/projects` | Create project | JSON: manufacturer, model, msn, mpd_dataset_id?, registration? | `{id}` | Complete |
| GET | `/api/projects` | List projects | — | `[{id, msn, manufacturer, model, status}]` | Complete |
| GET | `/api/projects/{project_id}/report` | Report summary for project | — | Summary dict (total_workscope_tasks, matched_with_mpd, effective_tasks, applicability_tbc, unmatched_pending_review, placeholders) | Complete |
| GET | `/api/projects/{project_id}/matches` | Match list; optional `filter_type` | Query: filter_type? (matched, effective, tbc) | Array of match objects | Complete |
| POST | `/api/projects/{project_id}/workscope/upload` | Upload workscope file (Excel); parse into ParsedWorkscopeRow | Form: file | `{file_id, rows_parsed}` | Complete (Excel only) |
| POST | `/api/projects/{project_id}/match` | Run matching (exact + normalized) | — | `{exact, normalized}` | Complete |
| POST | `/api/projects/{project_id}/evidence/upload` | Upload modification evidence file | Form: file | `{id, status: "pending"}` | **Stub** (no extraction) |

### Aviation documents API (`/api/aviation`)

All require `X-API-Key` header **only if** `AVIATION_DOCS_API_KEY` is set in env; otherwise no auth.

| Method | Path | Description | Request | Response | Status |
|--------|------|-------------|---------|----------|--------|
| POST | `/api/aviation/upload` | Upload PDF or Excel; parse, persist, revision | Form: file | `{document_id, document_key, revision_index, confidence, parse_warnings}` | Complete |
| GET | `/api/aviation/documents` | List parsed documents | Query: latest_only=true | Array of doc summaries | Complete |
| GET | `/api/aviation/documents/{document_id}` | Full canonical JSON for document | — | Full stored raw_json | Complete |
| GET | `/api/aviation/documents/{document_id}/tasks` | Flat task list; filters: ata_chapter, service_interval, task_type, limit | Query params | `{document_id, count, tasks}` | Complete |
| GET | `/api/aviation/documents/{document_id}/validate` | Row count and confidence | — | `{document_id, confidence, parse_warnings, totals}` | Complete |
| POST | `/api/aviation/query` | Query tasks (for Perkins) | JSON: document_id?, ata_chapters?, task_references?, free_text?, limit (default 50) | `{source_document, aircraft, check_type, tasks, count, query_confidence}` | Complete |

---

## 4. Database schema

**Engine:** SQLite 3 (async aiosqlite). Path in container: `/app/data/mpd_workscope.db`; on host (Docker volume): `./data/mpd_workscope.db` (or `/opt/mpd-workscope/data/`).

**Current migration:** `8f1a9c2d1b07` (add_aviation_document_tables). Chain: `2c6ae3cbcd42` → `3a1b2c3d4e5f` → `8f1a9c2d1b07`.

### Tables and columns

- **audit_log**  
  id (PK), action, entity_type, entity_id, details, sanitized_payload_summary, created_at  
  Stores audit trail for sanitized AI payloads and sensitive operations.

- **mpd_datasets**  
  id (PK), manufacturer, model, revision, version, source_file, parsed_status, created_at, updated_at  
  Indexes: manufacturer, model, revision. One row per imported MPD (manufacturer/model/revision).

- **mpd_tasks**  
  id (PK), dataset_id (FK → mpd_datasets.id ON DELETE CASCADE), task_reference, task_number, task_code, title, description, section, chapter, threshold_raw, interval_raw, threshold_normalized, interval_normalized, interval_json, source_references, applicability_raw, applicability_tokens_normalized, job_procedure, mp_reference, cmm_reference, zones, zone_mh, man, access_items, access_mh, preparation_description, preparation_mh, skill, equipment, extra_raw, row_index  
  Indexes: dataset_id, task_reference, task_number, task_code.

- **users**  
  id (PK), username (unique), first_name, last_name, email, password_hash, role, active, created_at, updated_at  
  Index: username.

- **projects**  
  id (PK), manufacturer, model, mpd_dataset_id (FK → mpd_datasets.id), msn, tsn, csn, registration, selected_checks, status, created_at, updated_at  
  Index: mpd_dataset_id, msn.

- **project_checks**  
  id (PK), project_id (FK → projects.id ON DELETE CASCADE), check_code, check_name, last_done_*, next_due_*, notes  
  Index: project_id.

- **project_files**  
  id (PK), project_id (FK → projects.id ON DELETE CASCADE), file_type, original_name, stored_path, mime_type, sheet_index, parsed_status, created_at  
  Index: project_id.

- **applicability_conditions**  
  id (PK), project_id (FK → projects.id ON DELETE CASCADE), token, raw_expression, resolved, evidence_file_id (FK → project_files.id), created_at  
  Index: project_id.

- **project_condition_answers**  
  id (PK), project_id (FK → projects.id ON DELETE CASCADE), condition_token, answer, source, created_at  
  Index: project_id.

- **modification_evidence_files**  
  id (PK), project_id (FK → projects.id ON DELETE CASCADE), original_name, stored_path, extracted_conditions, validation_status, created_at  
  Index: project_id.

- **parsed_workscope_rows**  
  id (PK), project_id (FK → projects.id ON DELETE CASCADE), project_file_id (FK → project_files.id), row_index, sheet_index, task_ref_raw, service_check_raw, description_raw, reference_raw, raw_row_json, row_type, confidence, created_at  
  Index: project_id.

- **workscope_match_candidates**  
  id (PK), parsed_row_id (FK → parsed_workscope_rows.id ON DELETE CASCADE), mpd_task_id (FK → mpd_tasks.id), match_type, confidence, reason, requires_confirmation, created_at  
  (Not currently populated by run_initial_matching; matching writes only to workscope_matches.)

- **workscope_matches**  
  id (PK), project_id (FK → projects.id ON DELETE CASCADE), parsed_row_id (FK → parsed_workscope_rows.id ON DELETE CASCADE), mpd_task_id (FK → mpd_tasks.id), match_type, confidence, reason, applicability_status, applicability_reason, applicability_raw, user_confirmed, created_at, updated_at  
  Index: project_id.

- **project_reports**  
  id (PK), project_id (FK → projects.id ON DELETE CASCADE), report_type, summary_json, file_path, created_at  
  Index: project_id.

- **aviation_documents**  
  id (PK, UUID string), document_key, revision_index, is_latest, source_filename, stored_path, content_sha256, parsed_at, confidence, parse_warnings (JSON), header_json, totals_json, raw_json, created_at, updated_at  
  Indexes: document_key, is_latest, content_sha256.

- **aviation_document_tasks**  
  id (PK), document_id (FK → aviation_documents.id ON DELETE CASCADE), section_type, line_number, service_interval, task_reference, ata_chapter, ata_derived, description, man_hours, task_type, ad_reference, component_pn, component_sn, component_position, component_description, status, raw_line, extra_fields (JSON)  
  Indexes: document_id, section_type, line_number, service_interval, task_reference, ata_chapter, task_type.

- **aviation_document_parts**  
  id (PK), document_id (FK → aviation_documents.id ON DELETE CASCADE), task_reference, part_number, description, part_type, unit, quantity, raw_line, extra_fields (JSON)  
  Indexes: document_id, task_reference, part_number.

---

## 5. Services and matching engine

### Workscope import (project flow)

- **Entry:** `POST /api/projects/{project_id}/workscope/upload` (single file).  
- **Detection:** `workscope_import.detect_file_type(filename)` → `excel` | `pdf` | `unknown`.  
- **Excel path:** File saved under `data/uploads/`; `ProjectFile` created; `parse_workscope_excel()` called with sheet_index=0 and no column_mapping → heuristic `detect_columns_heuristic(headers, rows)` maps headers to task_ref, service_check, description, reference; each data row becomes a `ParsedWorkscopeRow` with task_ref_raw, service_check_raw, description_raw, reference_raw, raw_row_json, row_type, confidence=0.8.  
- **PDF path:** Not implemented for project workscope; only Excel is used.  
- **Column mapping:** Heuristic only; no UI step to confirm or override mapping for this API. (The MPD import wizard has a full mapping UI; workscope does not.)

### Aviation document import (separate pipeline)

- **Entry:** `POST /api/aviation/upload`.  
- **Detection:** PDF vs Excel by extension.  
- **PDF:** `parser_pdf_soma.parse_pdf_soma(path)` — pdfplumber character-level extraction, column breaks from header or inferred from task-reference positions, section detection (AIRCRAFT_TASKS, COMPONENT_TASKS, DIRECTIVES, PARTS), row reconstruction with continuation lines and split task IDs; ATA derived from task reference; row-count validation.  
- **Excel:** `parser_excel.parse_excel_generic(path)` — openpyxl, merged cells expanded, hidden rows/cols skipped, header row detected by keyword score, fuzzy column mapping (rapidfuzz) to canonical fields; multiple sheets supported.  
- **Persist:** `aviation_docs.service.ingest_document()` — document_key derived (e.g. registration::work_order::check_type or filename); previous latest for same key set is_latest=false; new row with revision_index incremented; full canonical JSON in raw_json; tasks and parts inserted; optional reconstruction of task reference from digits in service_interval (e.g. 242 + 000-22-1- → 242000-22-1-).

### MPD matching engine

- **Entry:** `POST /api/projects/{project_id}/match`.  
- **Flow:** `matching.run_initial_matching()` deletes existing `WorkscopeMatch` for the project, then:  
  1. **Exact match:** For each `ParsedWorkscopeRow`, look up `MPDTask` by task_reference or task_number; if found, create `WorkscopeMatch` with match_type=`exact`, confidence=1.0, applicability_status=TBC.  
  2. **Normalized match:** For rows not yet matched, match on normalized key (strip + upper); create `WorkscopeMatch` with match_type=`normalized`, confidence=0.95, applicability_status=TBC.  
- **Not implemented:** Pattern-based matching, AI-assisted matching, and writing to `WorkscopeMatchCandidate`; applicability resolution (user/evidence) is implemented in `applicability.evaluate_task_applicability` / `set_match_applicability` but not exposed by API/UI for bulk resolution.

### Current state summary

| Component | State |
|-----------|--------|
| Workscope Excel import | Complete; heuristic columns; single sheet (0) |
| Workscope PDF import (project) | Not implemented |
| Aviation PDF (SOMA) | Complete; row counts and task refs mostly correct; some edge splits |
| Aviation Excel | Complete; generic fuzzy mapping, multi-sheet |
| Exact match | Complete |
| Normalized match | Complete |
| Pattern / AI match | Not implemented |
| Applicability evaluation | Logic in service; no API/UI for setting answers or evidence |

---

## 6. AI integration

### What the `ai/` folder does

- **ai/memory.py**  
  **RuleMemory:** In-memory list of reusable rules (e.g. type, pattern, metadata); used for “column_mapping” type in prompt context. **ProjectMemory:** Per-project in-memory list of key/value entries; isolated by project_id. **PromptContextBuilder:** Builds context for structure detection (sheet_headers, row_sample sanitized, reusable_rules).  
  Persistence: in-memory only; no DB or Redis yet.

- **ai/sanitizer.py**  
  Prepares payloads for external AI: sanitize_task_fragment, sanitize_column_sample, sanitize_for_structure_inference (headers + redacted row_sample). Logs what was sent via log_sanitized_sent (writes to `data/audit_ai_sanitized.log`).

- **ai/redaction.py**  
  Redacts serial-like numbers and registration-like strings (SERIAL_LIKE, REG_LIKE); redact_string, redact_dict, redact_for_ai. Used before any payload is sent to AI.

- **ai/prompt_templates.py**  
  SYSTEM prompts for structure detection and matching hints; no few-shot examples injected yet (LATER comments).

- **ai/providers/base.py**  
  Abstract BaseAIProvider: complete(system_prompt, user_content, max_tokens), structure_suggestion(sanitized_payload).

- **ai/providers/grok.py**  
  GrokProvider: calls x.ai API (grok-2-latest); complete and structure_suggestion implemented; used when AI_PROVIDER=grok and GROK_API_KEY set.

- **ai/providers/openai.py**  
  OpenAIProvider: stub; complete and structure_suggestion return "" and {}.

### What calls are made to external AI

- **Currently:** No automatic HTTP calls from the app to Grok/OpenAI in the main flows. The structure_suggestion path (column mapping suggestion from sanitized payload) is implemented in Grok but not wired from the workscope or MPD import UI. So in practice, no external AI is called unless you add a call (e.g. from an admin or import step).
- **When used:** If a caller builds a sanitized payload and uses GrokProvider.structure_suggestion(), it would POST to `https://api.x.ai/v1/chat/completions` with the structure-detection system prompt and the sanitized JSON.

### RuleMemory and ProjectMemory store

- **RuleMemory:** List of dicts: `{type, pattern, metadata}`. Intended for reusable parsing/matching rules (e.g. column_mapping). Not persisted; lost on restart.
- **ProjectMemory:** Dict mapping project_id → list of `{key, value}`. Intended for project-isolated session or context; not persisted; lost on restart.

---

## 7. Deployment

- **Server:** Same host as other Noteify apps (see SERVER_SETUP.md). DNS: **mpd.noteify.us** → server public IP.  
- **App URL:** https://mpd.noteify.us (Nginx + certbot).  
- **Docker:** Single service `app`; build from Dockerfile; volume `./data` → `/app/data`; port 8084; env_file `.env`.  
- **Nginx:** `scripts/setup-nginx.sh` creates `/etc/nginx/sites-available/mpd.noteify.us` (proxy to 127.0.0.1:8084, client_max_body_size 50m); enable and reload nginx; then run certbot for TLS.  
- **Process:** No systemd for the app itself; Docker Compose runs the container; entrypoint runs `alembic upgrade head` then `uvicorn main:app --host 0.0.0.0 --port 8084`.  
- **Deploy update:** SSH to server; `cd /opt/mpd-workscope`; `git pull`; `./scripts/deploy.sh` (which runs `docker compose up -d --build`). Verify: `curl -s https://mpd.noteify.us/health`.

Ports on host (do not reuse): 8084 = Scopewrath; 8080/8082 = AC Tracker; 9080/9082 = sandbox; 8088 = Schicchi; 3010 = CTA; etc. (see SERVER_SETUP.md).

---

## 8. Environment variables

From `.env.example` and code:

| Variable | Purpose | Example / default | Set on server |
|----------|---------|-------------------|---------------|
| PORT | Uvicorn port | 8084 | Yes (8084) |
| DATABASE_URL | Async DB URL | sqlite+aiosqlite:///.../data/mpd_workscope.db | Default if unset |
| DATABASE_URL_SYNC | Used by Alembic (sync driver) | Derived from DATABASE_URL | Derived |
| AI_PROVIDER | Which AI provider | grok \| openai \| anthropic | grok |
| GROK_API_KEY | x.ai API key for Grok | (empty) | Optional |
| OPENAI_API_KEY | OpenAI key (stub provider) | (empty) | Optional |
| ANTHROPIC_API_KEY | Anthropic key | (empty) | Optional |
| AVIATION_DOCS_API_KEY | If set, aviation API requires X-API-Key header | (empty) | Not in .env.example; add if Perkins/auth needed |

Which are set on server: not specified in repo; assume at least PORT=8084 and optionally GROK_API_KEY; DATABASE_URL left default (SQLite in `./data`).

---

## 9. SSH access

- **Host:** Same as “actracker” (e.g. `actracker-vps` in `~/.ssh/config`), or `deploy@<server-ip>`.  
- **Repo on server:** `/opt/mpd-workscope` (clone as deploy user; `sudo chown -R deploy:deploy /opt/mpd-workscope`).  
- **Connect:** `ssh actracker-vps` or `ssh deploy@<ip>`.  
- **Deploy:** From server, `cd /opt/mpd-workscope && ./scripts/deploy.sh`.  
- **Logs:** `docker compose logs -f` in `/opt/mpd-workscope`.

---

## 10. Current open tasks and known bugs

- **Session secret:** Move `SessionMiddleware` secret to env (e.g. `SESSION_SECRET_KEY`); currently hardcoded in main.py.  
- **Aviation API auth:** Document and optionally add `AVIATION_DOCS_API_KEY` to `.env.example`; if set, all aviation endpoints require `X-API-Key`.  
- **Aviation PDF extractor:** Tighten SOMA parser so all task references are complete (e.g. trailing `-R`/`-L` on split lines); ensure service_interval is clean and row counts match across all section types.  
- **Workscope PDF (project flow):** Not implemented; only Excel.  
- **OCR:** Scanned PDF path (aviation or workscope) not implemented; parser_pdf_soma returns “OCR required” for no-text PDFs.  
- **Evidence upload (Phase 2):** Extract conditions from uploaded evidence files and map to applicability tokens; UI for resolving TBC.  
- **Report Phase 2:** Implement effective_not_in_workscope, extra_in_workscope_not_in_mpd, not_required_for_selected_checks.  
- **Matching:** Add pattern-based and AI-assisted layers; optionally populate WorkscopeMatchCandidate for user confirmation.  
- **OpenAI provider:** Replace stub with real API calls when needed.  
- **AI structure suggestion:** Wire Grok (or OpenAI) structure_suggestion into workscope or MPD import UI if column-mapping assistance is desired.  
- **Perkins integration:** See section 11 (workscope query endpoints, rule-request endpoint, etc.).

---

## 11. Integration points with Perkins (perkins.noteify.us)

### What Perkins already uses

- **Base URL:** https://mpd.noteify.us (Scopewrath).  
- **Endpoints in use:**  
  - `GET /api/mpd/datasets` — List MPD datasets.  
  - `GET /api/mpd/datasets/{dataset_id}/tasks?section=32&limit=5&offset=0` — List MPD tasks (optional ATA filter).  
- **Auth:** None on these read-only endpoints currently.

### What still needs to be built on the Scopewrath side for full integration

- **Workscope / aviation query endpoints for Perkins:**  
  Already implemented: `POST /api/aviation/query` and `GET /api/aviation/documents/{id}/tasks` (and related aviation endpoints). Perkins can call these to get verified workscope/aviation task data (by document_id, ata_chapters, task_references, free_text) to cross-check against MPD.  
  - If Perkins is to use these from an external host, either leave `AVIATION_DOCS_API_KEY` unset (internal only) or set it and have Perkins send `X-API-Key`.  
  - Optional: dedicated “workscope for project” query (e.g. by project_id + filters) that returns normalized task list for a project’s parsed workscope (today project workscope is Excel-only and stored in parsed_workscope_rows; no unified query like aviation’s).

- **Rule-request endpoint:**  
  Not implemented. If Perkins needs to request or pull “rules” (e.g. column mapping rules, matching hints) from Scopewrath, add e.g. `GET /api/rules` or `POST /api/rules/request` that returns RuleMemory contents (or a subset) in a safe, sanitized form. RuleMemory is currently in-memory only; consider persisting if rules are to be shared across restarts or instances.

- **Unified “workscope + MPD” context for Perkins:**  
  Optional: an endpoint that, given project_id or document_id, returns both MPD tasks (for the project’s selected MPD) and workscope/aviation tasks in one response so Perkins can do one call for cross-check context. Today Perkins can get MPD tasks by dataset_id and aviation tasks by document_id separately.

- **Auth for external callers:**  
  Read-only MPD endpoints have no auth. Aviation API supports optional API key. For production, consider API key or JWT for Perkins for all integration endpoints and document which key Perkins uses.

---

*End of handover document.*
