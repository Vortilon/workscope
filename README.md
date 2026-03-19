# Scopewrath

Production-ready MVP for **aircraft maintenance workscope validation** against manufacturer MPDs (Maintenance Planning Documents).

## Features

- **MPD Management**: Upload/import MPD datasets by manufacturer, model, revision; normalized task storage (raw + normalized intervals/applicability).
- **Projects**: One project per aircraft MSN; select MPD revision, upload workscope.
- **Workscope Import**: Excel (and PDF stub); column detection with user confirmation; parsed rows stored locally.
- **Matching Engine**: Deterministic exact and normalized matching first; optional AI-assisted structure only (sanitized); user confirmation for ambiguous.
- **Applicability/Effectivity**: YES | NO | TBC; plain-language reasons; evidence upload (Phase 2).
- **Reporting**: Clickable counts (total, matched, effective, TBC, unmatched) with task lists and reasons.
- **Data Privacy**: No proprietary/confidential data sent to external AI; sanitization layer and audit log.

## Stack

- **Backend**: Python 3.12, FastAPI, Uvicorn
- **DB**: SQLite (MVP); designed to upgrade to Postgres (SQLAlchemy + Alembic)
- **Frontend**: Jinja2 + Tailwind CSS + Flowbite + HTMX + Alpine.js; **Tabulator** (tables, sort/filter); **ApexCharts** (charts); DAE colours and logo (Salient-style dashboard)
- **Excel**: openpyxl; PDF/OCR stubs for Phase 3
- **AI**: Provider-agnostic (Grok, OpenAI stub); sanitizer, redaction, rule/project memory

## Setup

```bash
python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env
# Edit .env: PORT, optional GROK_API_KEY / OPENAI_API_KEY
alembic upgrade head   # or: python -m alembic upgrade head
uvicorn main:app --reload --port 8084
```

Open http://localhost:8084 (web UI) and http://localhost:8084/docs (API).

## Docker

The container **runs migrations on startup** (see `entrypoint.sh`), so no separate migration step is needed.

```bash
docker compose up -d --build
# App on port 8084
```

To run migrations only (e.g. in CI or manually):  
`docker compose run --rm app python -m alembic upgrade head`

## Environment

| Variable | Purpose |
|----------|---------|
| `PORT` | Server port (default 8084) |
| `DATABASE_URL` | SQLite (default) or Postgres URL |
| `GROK_API_KEY` | Optional; for AI-assisted structure (sanitized only) |
| `OPENAI_API_KEY` | Optional; stub provider |
| `AI_PROVIDER` | grok \| openai \| anthropic |

See `.env.example`. Never commit secrets.

## Architecture

- **app/config.py**: Paths, DB URL, AI keys
- **app/database.py**: Async SQLAlchemy session
- **app/models/**: MPD, Project, Workscope, Report, Audit
- **app/services/**: MPD import, workscope import, normalize, matching, applicability, reporting
- **app/routes/**: Web (Jinja) and API (JSON); evidence upload (Phase 2)
- **ai/**: sanitizer, redaction, providers (base, grok, openai), memory (RuleMemory, ProjectMemory), prompt_templates

## Workflow

1. **MPD Library** – Upload MPD Excel (API: POST /api/mpd/upload).
2. **New Project** – Create project for one MSN; select MPD.
3. **Upload Workscope** – POST /api/projects/{id}/workscope/upload.
4. **Review Columns** – (UI or API) confirm task_ref, description, etc.
5. **Run Matching** – POST /api/projects/{id}/match.
6. **Review Applicability** – Resolve TBC with evidence (Phase 2).
7. **View Report** – /report/{project_id}; clickable counts.

## External read-only integration

If you need to connect an **external Python/FastAPI application** to Scopewrath MPD data in **read-only** mode:

- **Recommended (external networks/IPs):** Use the **read-only HTTPS API**:
  - `GET /api/mpd/datasets` – list MPD datasets
  - `GET /api/mpd/datasets/{dataset_id}/tasks?section=32&limit=5&offset=0` – list MPD tasks (optional ATA filter)
- **Same-host option:** Read the SQLite DB file directly in read-only mode (SQLite has no users):
  - Host path (Docker deploy): `/opt/mpd-workscope/data/mpd_workscope.db`
  - Open read-only using URI: `file:/opt/mpd-workscope/data/mpd_workscope.db?mode=ro`

Full details (tables/columns, sample SQL, network notes): `docs/EXTERNAL_DB_READONLY.md`.

## Server Deploy

See `docs/SERVER_SETUP.md`. Deploy to `/opt/mpd-workscope`; Nginx for mpd.noteify.us → 8084; certbot for TLS.

## License

Proprietary / as per org policy.
