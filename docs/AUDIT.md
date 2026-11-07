# AUDIT — Mirrorhub (Step 0)

Tarikh: 2026-11-08 · Persekitaran: Windows 11 Home 10.0.26200, AMD Ryzen 5 7535HS (6C/12T), 23.2 GB RAM, C: bebas ~18 GB, virtualization firmware = enabled.
Semua dakwaan di bawah diperoleh daripada arahan/pembacaan kod pada tarikh ini, bukan daripada `CLAUDE.md`.

## 1. Status repository

| Item | Fakta | Bukti |
|---|---|---|
| Git | Folder kerja **bukan** repo git sebelum audit. Baseline commit `f0688a7` dicipta (branch `main`), kerja di `dev/desktop-v1`. | `git log --oneline` |
| GitHub `marketerhubmy-dotcom/mirrorhub` | **Kosong** (tiada ref). Tiada sejarah untuk dipulihkan; folder ini ialah satu-satunya sumber. **Belum di-push** (menunggu kelulusan pemilik). | `git ls-remote` → exit 0, tiada output |
| Rahsia | `backend/.env` mengandungi `OPENAI_API_KEY`; di-ignore, tidak di-commit. | `.gitignore`, `git diff --cached` |
| Dokumen plan | Plan wujud sebagai `.pdf`; tiada `Mirrorhub_Master_Development_Plan.md` dalam workspace. | direktori |

## 2. Toolchain tempatan

| Alat | Status |
|---|---|
| Python 3.14.4, venv `backend/.venv` | ada |
| Node 24.15.0 / npm | ada |
| Git 2.53 | ada |
| MSVC Build Tools (VS 18) | ada |
| WebView2 runtime 157.x | ada |
| **Rust / cargo** | **TIADA** → Tauri 2 tidak boleh dibina tanpa pemasangan |
| **PyInstaller, Inno Setup, NSIS, WiX** | **TIADA** |
| Java / Android SDK / emulator | TIADA (blocker Fasa 06) |
| `gh` CLI | TIADA |
| ADB (bundled, v1.0.41 / 37.0.0) & scrcpy 4.0 | ada (`tools/scrcpy/…`), tidak boleh diredistribusi tanpa semakan lesen |
| Telefon disambung | **0** (`adb devices -l` kosong; `tools/last_device.txt` = `192.168.1.109:33587`, port WiFi mungkin lapuk) |

## 3. Apa yang sebenarnya ada (jauh melebihi `CLAUDE.md`)

Backend FastAPI (~150 fail .py): `agents/` (AI agent layer), `campaign/` (queue/scheduler), `orchestrator/` (fleet health/failover), `workflows/` (recorder/player), `vision/`, `execution/` (YouTube Create→TikTok, ~75 KB), `content/`, `apps/{tiktok,youtube_create}`, `api/` (devices, mirror, products, quicklaunch, automation, system), `websocket/`.
Frontend React+Vite+Tailwind: 20 halaman (Dashboard, DevicePage, DeviceWall, Automation, Pipeline, ContentStudio, Campaign, Orchestrator, Vision, Workflow*, TikTok, QuickLaunch, Settings, About, …).
`android-agent/`: aplikasi Kotlin (MediaProjection + Accessibility) — tidak dibina/diuji (tiada Gradle/JDK).
Shell desktop: `backend/desktop.py` = pywebview + uvicorn thread pada 127.0.0.1:8000.

**Pemerhatian penting:** kod sedia ada sangat berat pada pipeline TikTok/AI/kempen; produk dalam plan (multi-phone wall + device manager) hanyalah sebahagian kecil.

## 4. Baseline ujian

| Semakan | Hasil |
|---|---|
| `frontend: tsc --noEmit` | PASS (0 error) |
| `frontend: npm run build` | PASS (76 modul, 431 kB JS) |
| `backend: pytest` | **106 pass / 30 fail** (136). Gate coverage `fail-under=60` gagal (jumlah 14%). |

Punca 30 kegagalan (dari `--tb=line`):
- ~22 **ujian lapuk** — merujuk fungsi yang tidak lagi wujud (`_run_read_phase`, `get_pending_jobs`, `_launch_scrcpy`, `_launch_scrcpy_blocking`, `_processes`, `_find_stalled_jobs`, `is_device_busy`) atau kolum model yang tidak wujud (`AgentGoal.device_id`, `DeviceProfile.platform`). Ujian tidak membuktikan tingkah laku sebenar.
- 2 **kegagalan sebenar**: FK tidak dikuatkuasakan (`DID NOT RAISE IntegrityError`; baris `job` yatim kekal selepas `campaign` dipadam).
- 2 **pelanggaran konvensyen sebenar**: `h264_stream.py` / `device_stream.py` menduplikasi `_adb()` dan path scrcpy keras (`test_adb_path`).
- 1 `test_datetime_usage` (tz-aware), 1 `test_load_balancer`.

## 5. Streaming: status sebenar "Device Wall"

- `DeviceWallPage.tsx` = **halaman status fleet** (kad + skor, `/ws/orchestrator/fleet`). **Tiada video.** Bukan Device Wall yang dimaksudkan plan.
- `Start Mirror` = `scrcpy.exe` sebagai **tetingkap berasingan** (`services/scrcpy.py`). Plan: *tidak diterima sebagai output akhir*.
- Laluan lain wujud: `adb exec-out screenrecord` → `/ws/video/{id}` → WebCodecs (`useH264Stream.ts`); dan polling `screencap` JPEG (`device_stream.py`).
  - Masalah `screenrecord`: had masa ~180 s per sesi (proses tamat), saiz hardcoded `540x1200`, tiada pengendalian rotation/reconnect, tiada kawalan FPS/backpressure, perlu proses baru per penonton; pemisah NAL buffer dalam JS O(n²) pada setiap mesej.
  - **Tidak pernah ditunjukkan berfungsi pada ≥2 telefon.** Status: NOT TESTED.

## 6. Kawalan input & keselamatan (Rules 5, 8, plan §15)

| # | Temuan | Keterukan |
|---|---|---|
| S1 | `adb_control.input_text` hanya escape `\`, spasi, `'`. `'` → `\'` **dalam petikan tunggal** menutup petikan → *shell injection* pada peranti. `keyevent(code)` terus diinterpolasi tanpa validasi. Teks boleh datang daripada kandungan AI/scrape. | Tinggi |
| S2 | WebSocket (`/ws/control`, `/ws/video`, …) **tiada semakan Origin/token**. Mana-mana laman web dalam pelayar pengguna boleh sambung ke `ws://127.0.0.1:8000/ws/control/<id>`. `device_id` = `uuid5(DNS, adb_address)` → boleh diteka (IP:port). CORS default `*` + `allow_credentials=True`. | Tinggi |
| S3 | `control_endpoint` menelan semua exception (`except Exception: pass`), tiada validasi julat/jenis payload, tiada log audit per-device. | Sederhana |
| S4 | `desktop.py` bind `127.0.0.1` (baik); `run.py` bind `settings.host` — default perlu disahkan dan dikunci loopback. | Rendah–Sederhana |
| S5 | `ADB` hanya diurus melalui `shell` berterusan (stdout dibuang) → ralat arahan tidak kelihatan. | Sederhana |

## 7. Data & migrasi

- SQLite pada `backend/mirrorhub.db` (di dalam folder app → **tidak sesuai** untuk Program Files; perlu `%APPDATA%`).
- `migration.py` menambah lajur sahaja dengan backup (baik) tetapi Alembic (`alembic/versions/0001_baseline.py`) hanya baseline; `RELEASE_NOTES.md`/`CLAUDE.md` masih mengarahkan *"delete mirrorhub.db"* — bercanggah dengan plan §5.
- FK tidak dikuatkuasakan dalam sekurang-kurangnya satu laluan (lihat §4).

## 8. Lesen binari pihak ketiga (belum selesai)

scrcpy (Apache-2.0), ADB/platform-tools (Android SDK License — semak syarat redistribusi), FFmpeg DLL (`avcodec-62` dll — LGPL/GPL bergantung konfigurasi build), SDL3 (zlib), libusb (LGPL-2.1). **Status: belum disemak secara rasmi.** `tools/scrcpy/` dikecualikan daripada git sehingga semakan selesai.

## 9. Risiko utama

1. Embedded multi-stream belum terbukti pada hardware (tiada telefon dihubungkan dalam sesi ini).
2. Skop kod sedia ada sangat luas dengan ujian lapuk → risiko regresi senyap.
3. Pakej installer self-contained memerlukan alat yang belum dipasang.
4. Kelulusan pemilik diperlukan untuk: push ke GitHub, memasang toolchain (Rust/Inno Setup), semua kerja cloud/bayaran.
