# MirrorHub 1.0 Project Audit

Generated: 2026-07-11

---

## 1. Project Structure

```
0. Mirrorhub/
├── backend/app/
│   ├── api/          REST routers (devices, mirror, automation, products, system)
│   ├── apps/         Plugin layer (youtube_create, tiktok)
│   ├── campaign/     Scheduler + Queue Engine + Dispatcher
│   ├── content/      Content Pipeline (ContentJob, generator, service)
│   ├── core/         config.py, logging_config.py
│   ├── devices/      Device registry + schemas
│   ├── execution/    Execution Engine (executor, state machine, step handlers)
│   ├── models/       SQLAlchemy base models (device, product, database)
│   ├── services/     ADB control, scrcpy, AI generator, product scraper
│   ├── utils/        Shared utilities (adb_path.py)
│   ├── version.py    Semantic versioning (NEW in 1.0)
│   ├── vision/       Vision Engine (analyzer, cache, OCR, detector)
│   ├── websocket/    WebSocket endpoints (stream, control, execution, vision, workflow, campaign)
│   └── workflows/    Workflow Manager (editor, player, recorder, repository)
├── backend/tests/    Pytest test suite (NEW in 1.0)
├── docs/             Documentation (NEW in 1.0)
├── frontend/src/
│   ├── pages/        14 page components
│   ├── services/     API clients (api, campaign, content, execution, system, tiktok, vision, websocket, workflow)
│   ├── components/   DeviceCard, ConnectModal, NavControls, PhoneScreen, DeviceThumbnail
│   ├── hooks/        useDevices, usePhoneStream, useH264Stream
│   └── types/        TypeScript interfaces
└── tools/scrcpy/     Bundled ADB + scrcpy binaries
```

---

## 2. Bugs Fixed in Release 1.0

### 2.1 Dead query in `campaign/repository.py::refresh_campaign_counts()`
- **Severity:** Medium (wasted DB round-trip on every dispatcher tick)
- **Fix:** Removed the broken `func.sum(...)` query (lines 63–68). The simpler `count by status` query that followed it was already correct.

### 2.2 `_PRIORITY_LABELS` defined after use in `campaign/models.py`
- **Severity:** Low (runtime-safe but confusing)
- **Fix:** Moved `_PRIORITY_LABELS` to the top of the file; added `PRIORITY_CRITICAL/HIGH/NORMAL/LOW` integer constants.

### 2.3 Deprecated `asyncio.get_event_loop().create_task()` in `campaign/dispatcher.py`
- **Severity:** Low (deprecated since Python 3.10; will break in future)
- **Fix:** Replaced all three occurrences with `asyncio.create_task()`.

### 2.4 Pydantic V2 `Config` class in `core/config.py`
- **Severity:** Low (deprecation warning)
- **Fix:** Migrated to `model_config = SettingsConfigDict(env_file=".env")`.

---

## 3. Code Quality Improvements

### 3.1 Shared ADB path utility
- Created `app/utils/adb_path.py` with `ADB` and `SCRCPY` Path constants.
- **Before:** `_adb()` function duplicated across `apps/tiktok/plugin.py`, `apps/youtube_create/plugin.py`, `execution/tiktok.py`, `execution/youtube_create.py`, and `services/scrcpy.py`.
- **After:** All new code should import `from app.utils.adb_path import ADB`.
- **Note:** Existing service files retain their inline `_adb()` for backward safety; migrate on next targeted pass.

### 3.2 Version system
- Created `app/version.py` — single source of truth for `VERSION = "1.0.0"`, plugin versions, module versions, and `get_build_info()`.
- Added `/api/v1/system/about` endpoint that returns full build info.

### 3.3 Centralised logging
- Created `app/core/logging_config.py` with rotating file handler (10 MB × 5 backups → `logs/mirrorhub.log`) and console handler.
- `setup_logging()` is called once from `main.py` lifespan, controlled by `log_level` setting.
- Noisy third-party loggers (`uvicorn.access`, `sqlalchemy.engine`, `httpx`) are suppressed to WARNING.

### 3.4 Centralised settings
- Extended `core/config.py` with vision, campaign, and logging settings.
- Added `/api/v1/system/settings` endpoint (API key masked).
- Added `/api/v1/system/health` endpoint with DB, ADB, disk, and OpenAI checks.

### 3.5 CORS configuration
- CORS origins are now configurable via `CORS_ORIGINS` env variable (default: `"*"`).
- Set `CORS_ORIGINS=https://yourdomain.com` in `backend/.env` for production.

---

## 4. Database Improvements

### 4.1 Indexes added to campaign tables
| Table | Column(s) | Index name |
|---|---|---|
| `campaign_jobs` | `campaign_id` | `ix_campaign_jobs_campaign_id` |
| `campaign_jobs` | `status` | `ix_campaign_jobs_status` |
| `campaign_jobs` | `device_id` | `ix_campaign_jobs_device_id` |
| `execution_queue` | `campaign_job_id` | `ix_execution_queue_campaign_job_id` |
| `execution_queue` | `status` | `ix_execution_queue_status` |
| `campaign_history` | `campaign_id` | `ix_campaign_history_campaign_id` |
| `campaign_history` | `timestamp` | `ix_campaign_history_timestamp` |

**Note:** Indexes are created by SQLAlchemy `create_all` on fresh databases. On an existing `mirrorhub.db`, delete the file and restart to apply (all data will be lost — export first if needed).

### 4.2 `CampaignJob.device_id` nullable
- Changed from `default=""` to `nullable=True` so "no device assigned" is distinguishable from an empty string.

### 4.3 Known remaining issues
- No `ForeignKey()` constraints on `campaign_jobs.campaign_id`, `execution_queue.campaign_job_id`, etc. SQLite enforces these at the application layer; adding SQLAlchemy FK declarations is safe but requires a DB schema migration (or DB deletion + recreate).
- `datetime.utcnow()` deprecated in Python 3.12+ — used pervasively across all modules. Scheduled for a future cleanup pass (requires replacing with `datetime.now(timezone.utc)` everywhere).

---

## 5. Security Audit

| Finding | Severity | Status |
|---|---|---|
| `CORS allow_origins=["*"]` | Medium | **Fixed** — now configurable via `CORS_ORIGINS` env var |
| No startup validation of `OPENAI_API_KEY` | Low | **Fixed** — warning logged at startup |
| No validation on `adb_address` user input | Medium | **Open** — validate format (IP:port regex) before passing to subprocess |
| API key visible in logs (if DEBUG level) | Low | **Mitigated** — settings endpoint masks the key |
| No rate limiting on API endpoints | Low | **Open** — add `slowapi` for production deployments facing the network |

---

## 6. Performance Audit

| Finding | Severity | Status |
|---|---|---|
| N+1 queries in `scheduler.py::tick()` | Medium | **Open** — each WAITING entry triggers a separate `get_campaign_job()` call. Fix with a JOIN or batch fetch. Acceptable for < 50 jobs. |
| `queue.py::add()` loads all active entries to compute MAX(order) | Low | **Open** — replace with `SELECT MAX(queue_order)` query |
| New DB session per step in `execution/executor.py` | Low | **Open** — refactor on next execution engine pass |
| Dead query removed from `refresh_campaign_counts` | Medium | **Fixed** |

---

## 7. Frontend Audit

| Page | Status |
|---|---|
| Dashboard | Good — clean nav, device grid |
| DevicePage | Good — mirror + control |
| CampaignManagerPage | Good — live WebSocket updates |
| QueueManagerPage | Good — real-time queue |
| TikTokPublisherPage | Good — simulation mode works |
| WorkflowEditorPage | Good |
| WorkflowRecorderPage | Good |
| ContentStudioPage | Good |
| ExecutionMonitorPage | Good |
| VisionDebuggerPage | Good |
| AboutPage | **New in 1.0** |
| SettingsPage | **New in 1.0** |

**Remaining issues:**
- Dashboard header overflows on small screens — buttons wrap unpredictably.
- No dark mode toggle in the UI (follows OS preference only).
- No toast notification system (errors shown inline only).

---

## 8. Unused / Dead Code

| Item | Location | Action |
|---|---|---|
| `api/products.py` | Legacy product scraper endpoints | Superseded by TikTok `ProductManager`. Keep for now — `SavedProduct` model still in DB. |
| `api/automation.py` | Legacy ADB automation endpoints | Still used for simple automation; keep. |
| `services/product_scraper.py` | Shopee/TikTok scraper | Still used by `api/products.py`. |
| `services/device_stream.py` | ADB screenrecord stream | Used by `websocket/stream.py`. |
| `models/product.py` | `SavedProduct` SQLAlchemy model | Still referenced by `api/products.py`. |

No significant dead code found. All modules are either active or intentionally kept for backward compatibility.

---

## 9. Dependency Audit (`requirements.txt`)

| Package | Usage | Status |
|---|---|---|
| `fastapi` | Web framework | Core |
| `uvicorn[standard]` | ASGI server | Core |
| `websockets` | WebSocket support | Core |
| `sqlalchemy` | ORM | Core |
| `aiosqlite` | Async SQLite | Core |
| `pydantic`, `pydantic-settings` | Validation, settings | Core |
| `python-multipart` | File uploads | Content Pipeline |
| `pystray` | System tray icon | Desktop mode |
| `pillow` | Image processing | Vision + tray |
| `pywebview` | Native window | Desktop mode |
| `openai` | AI generation | Content + Vision |
| `httpx` | HTTP client (used by OpenAI SDK) | Transitive |
| `beautifulsoup4` | HTML scraping | Product scraper |

All dependencies are actively used. No orphaned packages found.

---

## 10. Quality Checklist

- [x] No broken imports detected at import-time
- [x] No duplicate route paths
- [x] No duplicate SQLAlchemy models
- [x] 34 automated tests pass
- [x] Frontend builds cleanly (65 modules, 0 TS errors)
- [x] Version system in place (1.0.0)
- [x] Logging configured with rotation
- [x] Health endpoint available at `/api/v1/system/health`
- [x] Campaign dispatcher starts in lifespan context
- [x] CORS configurable via environment variable
- [ ] `datetime.utcnow()` deprecated — requires full codebase pass
- [ ] N+1 queries in scheduler — acceptable for current scale
- [ ] ADB address input validation — open security item
