# MirrorHub Deployment Guide

Version: 1.0.0

---

## Prerequisites

| Requirement | Version | Notes |
|---|---|---|
| Windows | 10 / 11 | 64-bit required for bundled scrcpy |
| Python | 3.11+ | 3.14 tested |
| Node.js | 18+ | For frontend builds |
| Android device | API 29+ (Android 10+) | Wireless Debugging requires API 30+ |

---

## First-Time Setup

### 1. Install dependencies

Run `start.bat` from the project root. It will:
- Create `backend\.venv` and install Python packages
- Install Node packages in `frontend\node_modules`
- Build the React frontend into `frontend\dist`

Or manually:

```bat
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

cd ../frontend
npm install
npm run build
```

### 2. Configure API key

Create `backend\.env`:

```env
OPENAI_API_KEY=sk-...your-key-here...
```

Without this key, AI features (content generation, Vision Engine OCR via GPT-4o) are disabled. ADB automation and screen mirroring work without it.

### 3. Verify ADB is found

The bundled `adb.exe` is at:
```
tools\scrcpy\scrcpy-win64-v4.0\adb.exe
```

The health endpoint confirms it:
```
GET http://localhost:8000/api/v1/system/health
```

---

## Running the Application

### App Mode (production)

```bat
start.bat
```

Then choose option `[1]`. Opens a native pywebview window. No terminal stays open.

### Dev Mode (hot-reload)

```bat
start.bat
```

Choose option `[2]`. Opens two terminals:
- Backend: `http://localhost:8000`
- Frontend: `http://localhost:3000`

Access the app at `http://localhost:3000`.

### Manual start

```bat
cd backend
.venv\Scripts\activate
python run.py
```

---

## Connecting a Phone

1. Enable **Developer Options** (Settings → About Phone → tap Build Number 7 times)
2. Enable **Wireless Debugging** (Settings → Developer Options → Wireless Debugging → ON)
3. Note the IP:port shown on the Wireless Debugging screen
4. Click **+ Connect Phone** in the dashboard, enter the IP:port
5. Click **Start Mirror** on the device card

For the first connection on a new WiFi network, pair first:
1. On the phone: Wireless Debugging → **Pair device with pairing code**
2. Run `connect_phone.bat` and enter the pairing code

---

## Configuration Reference

Edit `backend\.env` to change settings. Restart the server after changes.

```env
# Required
OPENAI_API_KEY=sk-...

# Optional
CORS_ORIGINS=*                    # comma-separated origins or "*"
LOG_LEVEL=INFO                    # DEBUG | INFO | WARNING | ERROR
PORT=8000
DEVICE_TIMEOUT=30
OPENAI_MODEL=gpt-4o-mini
OPENAI_MAX_TOKENS=400
VISION_CACHE_TTL=5
VISION_POLL_INTERVAL=2.0
VISION_DEFAULT_TIMEOUT=30
CAMPAIGN_POLL_INTERVAL=5.0
CAMPAIGN_RETRY_DELAY=30.0
```

---

## Logs

Rotating log file: `backend\logs\mirrorhub.log`

- 10 MB per file, 5 backup files
- Format: `YYYY-MM-DD HH:MM:SS | LEVEL | module | message`
- Set `LOG_LEVEL=DEBUG` in `.env` for verbose output

---

## Database

SQLite file: `backend\mirrorhub.db`

**Reset the database** (clears all devices, jobs, campaigns):
```bat
del backend\mirrorhub.db
del /s /q backend\app\__pycache__
```
Then restart — SQLAlchemy recreates all tables automatically.

**Backup:**
```bat
copy backend\mirrorhub.db backup\mirrorhub_%date%.db
```

---

## Updating

1. Pull the latest code
2. Run `start.bat` → Dev Mode to rebuild frontend and reinstall packages
3. If models changed (new columns): delete `mirrorhub.db` and restart

---

## Troubleshooting

### App won't start
- Check `backend\logs\mirrorhub.log` for errors
- Run `GET /api/v1/system/health` for a status report
- Verify Python venv: `.venv\Scripts\python.exe --version`

### Phone not connecting
- Ensure phone and PC are on the same WiFi
- Check Wireless Debugging is still ON (it resets on reboot)
- Run `tools\scrcpy\scrcpy-win64-v4.0\adb.exe devices` to verify ADB sees the phone

### AI features not working
- Check `OPENAI_API_KEY` in `backend\.env`
- Check `GET /api/v1/system/health` — the `openai` check shows the key status

### Scrcpy window doesn't open
- Ensure no other process is using ADB (`adb kill-server`)
- Check that `tools\scrcpy\scrcpy-win64-v4.0\scrcpy.exe` exists

### Database errors after update
- Delete `mirrorhub.db` and all `__pycache__` directories
- Restart the backend

---

## Security Notes

- MirrorHub is designed for **local use only** (localhost).
- If exposing to a network, set `CORS_ORIGINS` to your specific origin.
- Never commit `backend\.env` to version control — it contains your API key.
- The `/api/v1/system/settings` endpoint masks the API key.
