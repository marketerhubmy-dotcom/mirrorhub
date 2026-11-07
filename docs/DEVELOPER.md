# MirrorHub Developer Guide

Version: 1.0.0

---

## Development Setup

```bat
git clone ...
cd "0. Mirrorhub"
start.bat  → [2]   # Dev mode
```

Backend reloads on file save. Frontend hot-reloads in browser.

---

## Running Tests

```bat
cd backend
.venv\Scripts\activate
pip install -r requirements-dev.txt
pytest
```

Run with coverage:
```bat
pytest --cov=app --cov-report=term-missing
```

Run a specific test file:
```bat
pytest tests/test_caption.py -v
```

---

## Adding a Step Handler

Step handlers are functions that execute a single ADB operation. They live in `execution/youtube_create.py` or `execution/tiktok.py`.

**Signature:**
```python
async def _my_step(job: ExecutionJob, step: dict) -> str | None:
    """Execute one step. Return error string on failure, None on success."""
    ...
```

**Register it** in the `HANDLERS` dict at the bottom of your platform file:
```python
HANDLERS: dict[str, Callable] = {
    "myplatform_my_step": _my_step,
    ...
}
```

**Use it** in a workflow by returning a step dict:
```python
{"type": "myplatform_my_step", "label": "Do something", "params": {...}}
```

---

## Adding a New Plugin

See [ARCHITECTURE.md](ARCHITECTURE.md#adding-a-new-plugin) for the full checklist.

Quick summary:
1. Create `app/apps/myplugin/` directory
2. Subclass `AppPlugin` in `plugin.py`
3. Create step handlers in `execution/myplugin.py`
4. Add 2 lines to `execution/executor.py`
5. Register routes in `api/router.py`
6. Build frontend page + service

---

## Database Changes

MirrorHub has no migration framework. SQLAlchemy's `create_all` creates missing *tables* but does not modify existing ones.

**To add a column:**
1. Add it to the SQLAlchemy model
2. Delete `backend/mirrorhub.db`
3. Delete all `__pycache__` directories
4. Restart — tables are recreated automatically

**Backup first:**
```bat
copy backend\mirrorhub.db backup\mirrorhub_pre_migration.db
```

---

## Logging

Use Python's standard `logging` module:

```python
import logging
logger = logging.getLogger(__name__)
logger.info("Starting job %s", job_id)
logger.warning("Device not responding")
logger.error("ADB command failed: %s", err)
```

Log output goes to both console and `backend/logs/mirrorhub.log`.

Set `LOG_LEVEL=DEBUG` in `backend/.env` for verbose output during development.

---

## WebSocket Broadcasts

Use the `manager` singleton from `app.websocket.manager`:

```python
from app.websocket.manager import manager
import json

# Broadcast to all execution monitors watching a device
await manager.broadcast_execution(device_id, json.dumps({
    "event": "step_completed",
    "step_index": 3,
    "progress": 0.6,
}))

# Broadcast to campaign/queue monitors
await manager.broadcast_campaign("queue", json.dumps({
    "event": "queue_update",
    "queue": [...],
    "counts": {...},
}))
```

---

## Configuration

All settings are in `app/core/config.py`. They are read from `backend/.env`.

To add a new setting:
```python
# In config.py
my_new_setting: int = 42
```

```env
# In .env
MY_NEW_SETTING=100
```

Access it anywhere:
```python
from app.core.config import settings
print(settings.my_new_setting)
```

---

## ADB Conventions

Always use the shared path:
```python
from app.utils.adb_path import ADB

proc = await asyncio.create_subprocess_exec(
    str(ADB), "-s", adb_address, "shell", "...",
    creationflags=subprocess.CREATE_NO_WINDOW,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
)
```

**Never use `shell=True`** — it bypasses `CREATE_NO_WINDOW` and risks command injection.

---

## Frontend Conventions

- Pages live in `src/pages/`, components in `src/components/`
- API clients live in `src/services/`
- Add new pages to `App.tsx` routes and `Dashboard.tsx` nav
- Use TailwindCSS utility classes
- Theme-aware: components should work in both light and dark mode (OS preference)
- WebSocket connections: open in `useEffect`, close on unmount

---

## Version Bumping

Edit `app/version.py`:
```python
VERSION = "1.1.0"
VERSION_TUPLE = (1, 1, 0)
```

Run tests:
```bat
pytest
```

Build frontend:
```bat
cd frontend && npm run build
```
