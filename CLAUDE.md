# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the app

**App Mode (production-like, pywebview window):**
```bat
start.bat  → [1]
```
Builds React, launches `backend\.venv\Scripts\pythonw.exe desktop.py` silently. No terminal stays open.

**Dev Mode (hot-reload, browser):**
```bat
start.bat  → [2]
```
Opens two terminals: backend on :8000, frontend on :3000. Access via `http://localhost:3000`.

**Manual backend only:**
```bat
cd backend
.venv\Scripts\activate
python run.py
```

**Manual frontend only:**
```bat
cd frontend
npm run dev
```

**Build frontend:**
```bat
cd frontend
npm run build
```

## Launcher mechanics (start.bat)

Uses a self-referencing trick (`if "%~1"=="--inside" goto :main`) to open a new terminal window, then `pushd "%~dp0"` so all paths are relative. This is required because the project path contains spaces (`addy RVSBD`, `0. Mirrorhub`). Always use relative paths in bat scripts; never use `%CD%` or hardcoded paths.

## Architecture

```
0. Mirrorhub/
├── backend/            FastAPI app, runs on :8000
│   ├── app/
│   │   ├── main.py     App entry: mounts API router, WebSockets, serves frontend dist/
│   │   ├── core/config.py  Settings via pydantic-settings, reads backend/.env
│   │   ├── api/        REST endpoints (devices, mirror, automation, products)
│   │   ├── models/     SQLAlchemy models (Device, SavedProduct) + database.py
│   │   ├── devices/    registry.py CRUD for Device table
│   │   ├── services/   scrcpy.py, adb_control.py, automation_runner.py,
│   │   │               ai_generator.py, product_scraper.py
│   │   └── websocket/  stream.py, control.py, video.py, manager.py
│   ├── desktop.py      pywebview entry: starts uvicorn in thread, opens native window
│   ├── run.py          Dev server entry (uvicorn with reload)
│   ├── requirements.txt
│   └── .env            OPENAI_API_KEY (user must fill in)
├── frontend/           React + Vite + TailwindCSS, proxies /api + /ws to :8000
│   └── src/
│       ├── pages/      Dashboard.tsx, DevicePage.tsx, AutomationPage.tsx
│       ├── components/ DeviceCard, ConnectModal, NavControls, PhoneScreen
│       ├── services/   api.ts (fetch wrapper), websocket.ts
│       ├── hooks/      useDevices.ts
│       └── types/      index.ts (Device, MirrorStatus, ControlCommand)
├── tools/scrcpy/scrcpy-win64-v4.0/   adb.exe + scrcpy.exe (bundled)
├── start.bat           One-click launcher (App Mode / Dev Mode)
├── mirror.bat          Reconnect phone + launch scrcpy directly
└── connect_phone.bat   First-time wireless pairing via adb pair
```

## Key patterns

**ADB path resolution** — all service files resolve ADB the same way, going 4 parents up from the service file to the project root:
```python
Path(__file__).parent.parent.parent.parent / "tools" / "scrcpy" / "scrcpy-win64-v4.0" / "adb.exe"
```

**Hide console windows** — every `subprocess.Popen` / `subprocess.run` / `asyncio.create_subprocess_exec` call uses `creationflags=subprocess.CREATE_NO_WINDOW`. This hides the CMD flash but still allows scrcpy's SDL window to appear.

**Persistent ADB shell** (`adb_control.py`) — one `subprocess.Popen` shell process is kept alive per device address. Commands are written to stdin. This is for low-latency control (tap/swipe/key) — much faster than spawning `adb shell` per command. The shell is auto-respawned if it dies.

**Database** — SQLite via `aiosqlite` at `backend/mirrorhub.db`. No migration framework. If you add a column, delete `mirrorhub.db` and restart (SQLAlchemy recreates all tables on startup via `Base.metadata.create_all`). Also delete `__pycache__` to avoid stale compiled models.

**Frontend in App Mode** — FastAPI serves `frontend/dist/` as static files. The catch-all route `/{full_path:path}` returns `index.html` for React Router. In Dev Mode, Vite's proxy handles `/api` and `/ws` routing to the backend.

**WebSocket control flow** — browser connects to `/ws/control/{device_id}`. Backend looks up `device.adb_address`; if set, dispatches directly via `adb_control`; otherwise forwards to Android agent via `manager.send_control()`.

## Device registration flow

1. User calls `POST /api/v1/mirror/connect` with `adb_address` (e.g. `192.168.1.5:37123`)
2. Backend runs `adb connect`, then upserts a `Device` row with `device_id = uuid5(DNS, adb_address)`
3. Mirror is started via `POST /api/v1/mirror/{device_id}/start` → launches scrcpy in a separate window
4. `scrcpy.py:start_mirror()` reconnects ADB first, then waits 1.5s to verify scrcpy didn't crash

## Automation system

`AutomationRunner` executes a list of step dicts sequentially:

| Step type | What it does |
|-----------|-------------|
| `open_app` | `adb shell monkey -p <package>` |
| `tap_rel` | Tap at relative (0–1) coordinates |
| `tap_text` | uiautomator dump → find element by text → tap center |
| `type_text` | `adb shell input text` line-by-line (sanitises special chars) |
| `push_file` | `adb push` + media scanner broadcast |
| `wait` | `asyncio.sleep` |
| `paste` / `select_all` | Ctrl+V / Ctrl+A keycodes |

`build_chatgpt_steps()` generates the ChatGPT app ADB steps.
`build_workflow()` generates the YT Create → TikTok steps.

## AI generation (ai_generator.py)

Uses `gpt-4o-mini` via OpenAI SDK. Two modes in `generate_scripts_for_angles`:
- **Custom format** (`custom_format` param set): AI fills in template placeholders (e.g. `[SCENE]`) — outputs a video creation prompt, not a script. Max 400 tokens.
- **Default**: Generates an 8-second VO script in Bahasa Malaysia. Max 80 tokens.

`generate_avatar_questions()` is called on every `fetch-product` to produce product-specific pain points / desires / triggers via `response_format={"type": "json_object"}`.

## Environment

- Python venv: `backend\.venv\` (created automatically by start.bat)
- Node modules: `frontend\node_modules\` (created automatically)
- `backend\.env` must contain `OPENAI_API_KEY=sk-...` for AI features
- Phone must be on same WiFi, with **Wireless Debugging ON** (Android 11+)
- `adb devices` should show the phone before clicking Start Mirror
