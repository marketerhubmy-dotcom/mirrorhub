# MirrorHub Architecture

Version: 1.0.0

---

## Overview

MirrorHub is a desktop application for managing multiple Android devices at scale. It mirrors device screens, sends ADB commands, runs automation workflows, generates AI content, and schedules publishing campaigns — all from a single local web UI.

**Runtime topology:**

```
Browser / pywebview window
        │  HTTP + WebSocket  (localhost:8000)
        ▼
  FastAPI backend  ──── SQLite DB (mirrorhub.db)
        │
        ├─ ADB (via bundled adb.exe)  ──── Android devices (WiFi)
        ├─ scrcpy.exe (screen mirror)
        └─ OpenAI API (AI features)
```

---

## Module Map

### `app/api/`
REST endpoints. Each file is an `APIRouter` included in `app/api/router.py`.

| File | Prefix | Purpose |
|---|---|---|
| `devices.py` | `/devices` | Device registration, list, delete |
| `mirror.py` | `/mirror` | ADB connect, scrcpy start/stop |
| `automation.py` | `/automation` | Legacy ADB automation |
| `products.py` | `/products` | Saved product CRUD |
| `system.py` | `/system` | Version, health, settings (v1.0) |

### `app/apps/`
Plugin layer. Each plugin is an `AppPlugin` subclass.

```
apps/
├── base.py              AppPlugin ABC + PluginResult dataclass
├── youtube_create/      YouTube Create Plugin (v1.0)
│   ├── plugin.py        YouTubeCreatePlugin
│   ├── workflow.py      Builds the step list for a job
│   ├── constants.py     Timeouts, package names, etc.
│   └── ...
└── tiktok/              TikTok Publisher Plugin (v1.0)
    ├── plugin.py        TikTokPlugin
    ├── workflow.py      Builds the step list for a job
    ├── caption.py       Caption builder + variable substitution
    ├── product.py       ProductManager (JSON-backed registry)
    └── ...
```

**Plugin interface** (`AppPlugin`):
- `validate(job)` — pre-flight check, no device access
- `launch(adb, device_id)` — open app, verify home screen via Vision
- `prepare(job, adb, device_id)` — push assets to device
- `execute(job, adb, device_id)` — build workflow, start execution (or simulate)
- `finish(job, adb, device_id)` — post-execution cleanup

### `app/campaign/`
Queue-based batch scheduler. Decouples job scheduling from execution.

```
campaign/
├── models.py      Campaign, CampaignJob, ExecutionQueue, CampaignHistory
├── schemas.py     Pydantic request/response models
├── repository.py  DB CRUD helpers
├── queue.py       QueueEngine — in-memory sorted queue (backed by DB)
├── scheduler.py   tick() — promotes WAITING→READY based on time + deps
├── dispatcher.py  run_loop() — background task; routes jobs to plugins
├── executor.py    Routes a CampaignJob to its plugin
├── planner.py     Dependency validation, schedule preview, estimates
└── routes.py      REST endpoints (/campaigns/*)
```

**Queue lifecycle:**
```
WAITING → READY → RUNNING → COMPLETED
                       └→ FAILED → RETRY → READY → …
Any → PAUSED → resume → previous state
Any → CANCELLED
```

**Priority:** 0=CRITICAL, 1=HIGH, 2=NORMAL (default), 3=LOW.

### `app/content/`
Content Pipeline. Stores `ContentJob` rows (scripts, captions, images) and generates AI content.

```
content/
├── models.py      ContentJob (DB model)
├── schemas.py     Pydantic models
├── repository.py  CRUD
├── generator.py   OpenAI calls for script + caption generation
├── service.py     Orchestrates generation + file handling
├── workflow.py    Links a ContentJob to a Workflow for execution
└── routes.py      REST + file upload endpoints
```

### `app/execution/`
Execution Engine. Runs a list of step dicts on a device via ADB.

```
execution/
├── executor.py          start_execution(), get_state(), STEP_HANDLERS dict
├── state_machine.py     ExecutionState, transitions, progress tracking
├── models.py            ExecutionJob (DB model)
├── device_session.py    is_device_busy() — per-device lock
├── progress.py          Progress broadcast via WebSocket
├── workflow_builder.py  Builds a step list from a Workflow DB row
├── youtube_create.py    HANDLERS for youtube_create_* steps
└── tiktok.py            HANDLERS for tiktok_* steps
```

**Adding a new platform:** Create `execution/myplatform.py` with a `HANDLERS: dict` of `step_type → async handler`. Then add two lines to `executor.py`:
```python
from . import myplatform as mp
STEP_HANDLERS = {**ytc.HANDLERS, **ttk.HANDLERS, **mp.HANDLERS}
```

### `app/vision/`
Vision Engine. Takes ADB screenshots, runs OCR / button detection, caches results.

```
vision/
├── analyzer.py     analyze_screen(), wait_until() — public API
├── cache.py        TTL cache (configurable via vision_cache_ttl)
├── screenshot.py   ADB screencap → PIL Image
├── ocr.py          pytesseract / OpenAI Vision OCR
├── detector.py     Button detection logic
├── matcher.py      Fuzzy text matching
├── providers.py    OCR provider abstraction
├── state.py        ScreenAnalysis dataclass
└── routes.py       REST + WebSocket endpoints
```

### `app/workflows/`
Workflow Manager. Stores reusable step sequences in the DB.

```
workflows/
├── models.py      Workflow, WorkflowStep, WorkflowVersion (DB models)
├── editor.py      Step add/remove/reorder, duplicate
├── recorder.py    Live recording session via WebSocket
├── player.py      Plays back a workflow by translating it to ExecutionEngine steps
├── repository.py  CRUD
├── serializer.py  Import/export JSON
├── validator.py   Pre-run validation
└── routes.py      REST endpoints
```

### `app/websocket/`
WebSocket endpoint modules. All share the `ConnectionManager` singleton.

| File | Route | Purpose |
|---|---|---|
| `stream.py` | `/ws/stream/{device_id}` | ADB agent → backend frame push |
| `video.py` | `/ws/video/{device_id}` | H264 stream to browser |
| `control.py` | `/ws/control/{device_id}` | Browser → ADB tap/key |
| `execution_stream.py` | `/ws/execution/{device_id}` | Live execution state |
| `vision_stream.py` | `/ws/vision/{device_id}` | Live ScreenAnalysis |
| `workflow_stream.py` | `/ws/workflow/{channel_id}` | Workflow/recorder events |
| `campaign_stream.py` | `/ws/campaign/{channel_id}` | Campaign/queue updates |

---

## Data Flow: Campaign Job to Published Post

```
User creates Campaign + CampaignJob
    ↓
POST /api/v1/campaigns/{id}/start
    ↓ enqueues CampaignJob into QueueEngine
Dispatcher tick() (every 5s)
    ↓ scheduler.tick() promotes WAITING→READY
    ↓ next_ready() picks highest priority entry
    ↓ checks device availability (is_device_busy)
    ↓ campaign/executor.dispatch(cj, device)
         ↓ builds job dict from ContentJob + job_config
         ↓ TikTokPlugin.execute(job, adb, device_id)
              ↓ validate() + build_workflow()
              ↓ execution/executor.start_execution(steps)
                   ↓ runs tiktok_* step handlers
                   ↓ broadcasts progress via WebSocket
Dispatcher watcher polls execution state
    ↓ on COMPLETED: mark queue COMPLETED, record history
    ↓ on FAILED:    retry (if retry_count < retry_max)
    ↓ broadcasts queue_update via /ws/campaign/queue
```

---

## ADB Path Convention

All code that needs `adb.exe` should use:

```python
from app.utils.adb_path import ADB
```

This resolves to `<project_root>/tools/scrcpy/scrcpy-win64-v4.0/adb.exe`.

**Legacy inline `_adb()` functions** exist in older service files. Migrate on next pass.

---

## Database Schema

SQLite via `aiosqlite`. File: `backend/mirrorhub.db`.

**No migration framework** — SQLAlchemy `create_all` on startup creates missing tables. To add a column: delete `mirrorhub.db` + `__pycache__` and restart.

Key tables:

| Table | Module | Purpose |
|---|---|---|
| `devices` | devices | Connected Android devices |
| `saved_products` | models/product | Legacy product registry |
| `content_jobs` | content | AI-generated content (scripts, captions) |
| `execution_jobs` | execution | One row per plugin execution run |
| `workflows` | workflows | Reusable step sequences |
| `workflow_steps` | workflows | Individual steps |
| `workflow_versions` | workflows | Version history |
| `campaigns` | campaign | Campaign header |
| `campaign_jobs` | campaign | One job per post/upload |
| `execution_queue` | campaign | Priority queue entries |
| `campaign_history` | campaign | Audit log |

---

## Configuration

All settings are in `core/config.py` and read from `backend/.env`.

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | `""` | Required for AI features |
| `CORS_ORIGINS` | `"*"` | Restrict in production |
| `LOG_LEVEL` | `"INFO"` | `DEBUG`/`INFO`/`WARNING`/`ERROR` |
| `CAMPAIGN_POLL_INTERVAL` | `5.0` | Dispatcher tick frequency (s) |
| `VISION_CACHE_TTL` | `5` | Screen analysis cache duration (s) |
| `PORT` | `8000` | Backend listen port |

---

## Adding a New Plugin

1. Create `app/apps/myplugin/` with `plugin.py` (subclass `AppPlugin`), `constants.py`, `workflow.py`.
2. Create `app/execution/myplugin.py` with `HANDLERS: dict`.
3. Add 2 lines to `app/execution/executor.py` (import + merge into `STEP_HANDLERS`).
4. Create `app/apps/myplugin/routes.py` and add to `app/api/router.py`.
5. Create frontend service + page, wire in `App.tsx` and `Dashboard.tsx`.
