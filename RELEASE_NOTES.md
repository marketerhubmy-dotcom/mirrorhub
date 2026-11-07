# MirrorHub Release Notes

---

## v1.0.0 — Stable (2026-07-11)

This is the first stable production release of MirrorHub.

### What's New

**Version System**
- `GET /api/v1/system/about` — build info, plugin versions, Python version, DB status
- `GET /api/v1/system/health` — health checks for DB, ADB, OpenAI API key, disk space
- `GET /api/v1/system/settings` — read-only settings view (API key masked)

**About Page**
- New frontend page at `/about` — shows version, system info, health checks, plugin list
- Accessible via the ℹ button in the dashboard header

**Settings Page**
- New frontend page at `/settings` — shows all configurable settings
- Accessible via the ⚙ button in the dashboard header

**Centralised Logging**
- Rotating log file: `backend/logs/mirrorhub.log` (10 MB × 5 files)
- Log level configurable via `LOG_LEVEL=DEBUG|INFO|WARNING|ERROR` in `.env`
- Clear startup message with version and OpenAI key status

**Configuration Improvements**
- New settings: `CORS_ORIGINS`, `OPENAI_MODEL`, `OPENAI_MAX_TOKENS`, `VISION_CACHE_TTL`, `VISION_POLL_INTERVAL`, `VISION_DEFAULT_TIMEOUT`, `CAMPAIGN_POLL_INTERVAL`, `CAMPAIGN_RETRY_DELAY`, `LOG_LEVEL`
- CORS origins configurable via environment variable (was hardcoded to `"*"`)

**ADB Path Utility**
- `app/utils/adb_path.py` — shared `ADB` and `SCRCPY` Path constants
- Eliminates duplicated `_adb()` functions across the codebase

**Testing Infrastructure**
- `backend/tests/` with pytest + pytest-asyncio
- 34 tests covering: campaign CRUD, caption builder, scheduler recurrence, dependency validation, version system
- `pytest.ini` + `requirements-dev.txt` for easy test setup

**Documentation**
- `docs/ARCHITECTURE.md` — full module map, data flows, conventions
- `docs/DEPLOYMENT.md` — setup, configuration, troubleshooting
- `docs/DEVELOPER.md` — development guide, conventions, how-tos
- `docs/API.md` — complete REST + WebSocket API reference
- `docs/AUDIT_1.0.md` — full project audit (bugs, security, performance, quality)

### Bug Fixes

- **Dead DB query removed** — `campaign/repository.py::refresh_campaign_counts()` ran a broken `func.sum()` query on every tick; removed (was silently discarded anyway)
- **`_PRIORITY_LABELS` moved to top of `campaign/models.py`** — was defined 67 lines after first use; safe at runtime but confusing
- **Deprecated `asyncio.get_event_loop().create_task()`** — replaced with `asyncio.create_task()` throughout `campaign/dispatcher.py` (deprecated since Python 3.10)
- **Pydantic V2 Config class** — migrated `core/config.py` to `model_config = SettingsConfigDict(...)` (removes deprecation warning)

### Database Changes

- Added 7 indexes on hot query columns in campaign tables (see `docs/AUDIT_1.0.md` §4.1)
- `CampaignJob.device_id` changed from `default=""` to `nullable=True`
- **Action required if upgrading:** delete `backend/mirrorhub.db` and restart to apply schema changes

### Included Releases

This release includes all prior incremental releases:

| Release | Feature |
|---|---|
| 0.1 | Device Manager + ADB connect + scrcpy mirror |
| 0.2 | Vision Engine + Execution Engine |
| 0.3 | Content Pipeline + AI generation |
| 0.4 | YouTube Create Plugin |
| 0.5 | Workflow Manager |
| 0.6 | Workflow Editor + Recorder (frontend) |
| 0.7 | TikTok Publisher Plugin |
| 0.8 | Campaign Scheduler + Queue Engine |
| 1.0 | Stability, logging, testing, documentation |

---

## Upgrade from 0.8 to 1.0

1. Pull latest code
2. Delete `backend/mirrorhub.db` (schema changed — indexes, nullable device_id)
3. Run `start.bat` → Dev Mode to reinstall packages + rebuild frontend
4. Copy your `backend/.env` — it is not modified by the upgrade

---

## Known Issues

- `datetime.utcnow()` used throughout the codebase — deprecated in Python 3.12+; scheduled for a future cleanup pass
- N+1 DB queries in `campaign/scheduler.py::tick()` — acceptable for < 100 concurrent queued jobs
- No rate limiting on API endpoints — MirrorHub is designed for localhost use only
- Dashboard header overflows on narrow screens
