# Read-only access to Scopewrath MPD data (external Python/FastAPI)

## 1. Database type and version

- **SQLite 3** (as used by Python 3.12 `sqlite3` / `aiosqlite`).
- The app uses the async driver `aiosqlite`; for an external read-only client you can use standard **sqlite3** (sync) or **aiosqlite** (async) in read-only mode.

---

## 2. Connection details

### File-based (SQLite)

- **Host / IP / port:** N/A. SQLite is file-based.
- **Database name / path:**  
  - **Inside the Scopewrath app container:** `/app/data/mpd_workscope.db`  
  - **On the server host (when using Docker volume):** `/opt/mpd-workscope/data/mpd_workscope.db`
- **Read-only username/password:** SQLite has no users. To enforce read-only access:
  - Open the database in read-only mode: use URI  
    `file:/path/to/mpd_workscope.db?mode=ro`  
    (e.g. in Python: `sqlite3.connect("file:/opt/mpd-workscope/data/mpd_workscope.db?mode=ro", uri=True)`).
  - Or use the **HTTP API** below (read-only endpoints; no DB credentials).

### Connection strings (for reference)

- **Sync (e.g. pandas, sync SQLite):**  
  `sqlite:////opt/mpd-workscope/data/mpd_workscope.db`  
  Read-only: open with `?mode=ro` in the path if your driver supports it.
- **Async (e.g. aiosqlite):**  
  `sqlite+aiosqlite:////opt/mpd-workscope/data/mpd_workscope.db`  
  For read-only, ensure the process only runs SELECTs (or use a copy of the file).

---

## 3. MPD-related tables and columns

### Table: `mpd_datasets`

| Column          | Type     | Description |
|-----------------|----------|-------------|
| id              | INTEGER  | Primary key. Dataset ID. |
| manufacturer    | VARCHAR(64) | Manufacturer (e.g. Airbus, Boeing, ATR). |
| model           | VARCHAR(64) | Model (e.g. A320, 737-800, ATR72). |
| revision        | VARCHAR(128) | Revision (e.g. R50, R37). |
| version         | VARCHAR(128) | Optional version string. |
| source_file     | VARCHAR(512) | Original filename. |
| parsed_status   | VARCHAR(32) | `pending` \| `in_progress` \| `done` \| `error`. |
| created_at      | DATETIME | Creation time. |
| updated_at      | DATETIME | Last update. |

**Indexes:** manufacturer, model, revision.

---

### Table: `mpd_tasks`

| Column                         | Type        | Description |
|--------------------------------|-------------|-------------|
| id                             | INTEGER     | Primary key. Task ID. |
| dataset_id                     | INTEGER     | FK → `mpd_datasets.id`. Which MPD dataset this task belongs to. |
| task_reference                 | VARCHAR(256)| Task reference / ref number. |
| task_number                    | VARCHAR(128)| Task number (often same as reference). |
| task_code                      | VARCHAR(128)| Task code. |
| title                          | VARCHAR(512)| Task title. |
| description                    | TEXT        | Task description. |
| section                        | VARCHAR(128)| Section (often ATA chapter, e.g. 32). |
| chapter                        | VARCHAR(128)| Chapter. |
| threshold_raw                  | VARCHAR(256)| Raw threshold text (e.g. T: 4 C for ATR). |
| interval_raw                   | VARCHAR(256)| Raw interval text (e.g. I: 4 C OR I: 16 YE). |
| threshold_normalized           | VARCHAR(256)| Normalized threshold string. |
| interval_normalized            | VARCHAR(256)| Normalized interval string. |
| interval_json                  | JSON        | Structured interval e.g. `{"value": 24, "unit": "MO"}` (when parsed). |
| source_references              | VARCHAR(512)| MRBR / CPCP / MPD references. |
| applicability_raw              | TEXT        | Effectivity as in MPD (e.g. PRE 4511 POST 2595 OR PRE 4511 POST 7378). |
| applicability_tokens_normalized| TEXT        | Tokenized effectivity (e.g. comma-separated or JSON). |
| job_procedure                  | VARCHAR(512)| Job procedure ref. |
| mp_reference                   | VARCHAR(256)| MP reference. |
| cmm_reference                  | VARCHAR(256)| CMM reference. |
| zones                          | VARCHAR(512)| Zone(s). |
| zone_mh                        | VARCHAR(64) | Zone man-hours. |
| man                            | VARCHAR(64) | Man. |
| access_items                   | VARCHAR(512)| Access items. |
| access_mh                      | VARCHAR(64) | Access man-hours. |
| preparation_description        | TEXT        | Preparation description. |
| preparation_mh                 | VARCHAR(64) | Preparation man-hours. |
| skill                          | VARCHAR(128)| Skill. |
| equipment                      | VARCHAR(512)| Equipment. |
| extra_raw                      | JSON        | Extra manufacturer-specific columns as key/value. |
| row_index                      | INTEGER     | Original sheet row index. |

**Foreign key:** `dataset_id` → `mpd_datasets.id` ON DELETE CASCADE.

**Indexes:** dataset_id, task_reference, task_number, task_code.

---

## 4. Sample query (MPD tasks for a given ATA chapter)

ATA chapter is typically in `section` or `chapter` (e.g. `"32"` or `"ATA 32"`). Example: return 3–5 tasks for “ATA 32” (or section 32):

```sql
SELECT
  t.id,
  t.dataset_id,
  d.manufacturer,
  d.model,
  d.revision,
  t.task_reference,
  t.task_number,
  t.title,
  t.section,
  t.chapter,
  t.threshold_raw,
  t.interval_raw,
  t.applicability_raw,
  t.zones,
  t.skill,
  t.row_index
FROM mpd_tasks t
JOIN mpd_datasets d ON d.id = t.dataset_id
WHERE (t.section LIKE '%32%' OR t.chapter LIKE '%32%')
  AND d.parsed_status = 'done'
ORDER BY t.dataset_id, t.row_index
LIMIT 5;
```

If your data uses a numeric section (e.g. `section = '32'`):

```sql
SELECT
  t.id,
  t.dataset_id,
  d.manufacturer,
  d.model,
  d.revision,
  t.task_reference,
  t.task_number,
  t.title,
  t.section,
  t.chapter,
  t.threshold_raw,
  t.interval_raw,
  t.applicability_raw
FROM mpd_tasks t
JOIN mpd_datasets d ON d.id = t.dataset_id
WHERE CAST(t.section AS INTEGER) = 32
  AND d.parsed_status = 'done'
ORDER BY t.row_index
LIMIT 5;
```

(Use the first query if section is text like `"32"` or `"ATA 32"`.)

---

## 5. Network access and options for external IP (72.62.175.45)

- The database file lives **inside the Scopewrath server** (container path `/app/data/mpd_workscope.db`, host path `/opt/mpd-workscope/data/mpd_workscope.db` when the volume is mounted).
- **Direct SQLite from 72.62.175.45:** SQLite is not a network server; there is no built-in way to connect to it from another host by IP/port. So the DB is **not** directly accessible from an external IP unless you:
  - Run your external app on the **same host** and open the file path above (e.g. `/opt/mpd-workscope/data/mpd_workscope.db`), or
  - Expose the file via NFS/SMB or copy it periodically to the external host, or
  - Use an **SSH tunnel** to the server and run your Python app over SSH (e.g. run the script on the server via SSH so it reads the local file).

**Recommended for external IP: use the Scopewrath HTTP API (read-only).**

- The app is served at **https://mpd.noteify.us** (and listens on port 8084).
- You can add **read-only API endpoints** (no auth or API key for now, or add a read-only key later) so your external Python/FastAPI app calls:
  - `GET /api/mpd` – list datasets.
  - `GET /api/mpd/datasets/{dataset_id}/tasks` – list tasks (with optional `section`, `limit`, `offset`).
- Then your external application at 72.62.175.45 uses **HTTPS** to this host; no direct DB connection is needed, and the app enforces read-only (SELECT only) behind these endpoints.

**Summary**

| Access type        | From external IP 72.62.175.45? | How |
|--------------------|----------------------------------|-----|
| Direct SQLite     | No (unless file is on that host or over NFS/tunnel). | Open `file:...?mode=ro` on a path visible to the client. |
| Scopewrath API    | Yes.                             | HTTPS to https://mpd.noteify.us (read-only endpoints). |
| SSH / run on server| Yes (from 72.62.175.45 to server). | SSH in and run Python script that opens local DB path. |

---

## 6. Read-only API (recommended for external IP)

From **72.62.175.45** (or any host) you can use HTTPS — no direct DB access.

- **Base URL:** `https://mpd.noteify.us` (or `http://<server>:8084` if not behind HTTPS).
- **List datasets:**  
  `GET /api/mpd/datasets`  
  Returns: `[{ "id", "manufacturer", "model", "revision", "parsed_status", "source_file", "created_at" }, ...]`.

- **List tasks for a dataset (optional ATA filter):**  
  `GET /api/mpd/datasets/{dataset_id}/tasks?section=32&limit=5&offset=0`  
  - `section` (optional): filter by ATA chapter (e.g. `32`); matches `section` or `chapter` containing that value.  
  - `limit` (default 100, max 1000).  
  - `offset` (default 0).  
  Returns: array of task objects with all MPD columns (task_reference, title, threshold_raw, interval_raw, applicability_raw, section, chapter, etc.).

**Example (verify structure for ATA 32, 3–5 rows):**

```bash
curl -s "https://mpd.noteify.us/api/mpd/datasets/1/tasks?section=32&limit=5"
```

Or from Python:

```python
import httpx
r = httpx.get("https://mpd.noteify.us/api/mpd/datasets/1/tasks", params={"section": "32", "limit": 5})
tasks = r.json()
```

No authentication is required for these read-only endpoints today; you can add an API key or auth later if needed.
