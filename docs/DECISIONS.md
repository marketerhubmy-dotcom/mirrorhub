# DECISIONS (ADR ringkas)

## ADR-001 — Shell desktop V1: kekalkan pywebview + FastAPI, tangguh Tauri
- **Konteks:** Plan §3 mencadangkan Tauri 2 "jika sesuai selepas audit". Audit: Rust/cargo tiada pada mesin ini; shell pywebview (`backend/desktop.py`) sudah wujud, WebView2 157 dipasang; backend Python ialah teras seluruh logik.
- **Keputusan:** V1 kekal pywebview + backend Python. Pakej dengan PyInstaller (onedir) + pemasang Inno Setup. Tauri dinilai semula selepas gate Release 1.0 (hanya jika ada keperluan konkrit: auto-update, tray, saiz).
- **Akibat:** tiada pemasangan Rust diperlukan; pemasang bergantung pada PyInstaller (pip, dalam venv) dan Inno Setup (pemasangan sistem — **perlu kelulusan pemilik**). Penyimpangan daripada plan ini sengaja dan direkodkan.

## ADR-002 — Embedded streaming: scrcpy-server `raw_stream` → WebSocket → WebCodecs
- **Konteks:** `adb screenrecord` ada had ~180 s, saiz tetap, tiada kawalan; tetingkap scrcpy berasingan tidak diterima (plan §1, rules #4).
- **Bukti:** `tools/scrcpy/scrcpy-win64-v4.0/scrcpy-server` (classes.dex) mengandungi pilihan `raw_stream`, `tunnel_forward`, `send_frame_meta`, `send_device_meta`, `send_dummy_byte`, `send_stream_meta`, `video_codec_options`, `max_size`, `max_fps`, `video_bit_rate`, `scid`. (Perhatian: `send_codec_meta` versi lama **tiada** → jangan andaikan protokol 3.x.)
- **Keputusan:** backend tolak `scrcpy-server` ke peranti, jalankan `app_process` dengan `raw_stream=true control=false audio=false tunnel_forward=true`, sambung melalui `adb forward` ke soket video, baca strim H.264 Annex-B mentah (tanpa framing), pisahkan NAL pada backend, cache SPS/PPS/IDR terakhir, siar ke semua penonton WS; pelayar nyahkod dengan WebCodecs ke `<canvas>`. Satu proses server per peranti (dikongsi antara penonton, thumbnail & fokus pada resolusi berbeza = sesi berasingan per profil).
- **Kenapa raw_stream:** menghapuskan risiko perubahan format framing antara versi scrcpy; cukup untuk video.
- **Kawalan:** laluan adb shell berterusan yang diperkuat (ADR-003). Kawalan melalui soket kawalan scrcpy ditangguh (perlu protokol 4.0 yang disahkan pada hardware).
- **Status:** kod + ujian unit terhadap strim sintetik. **Pengesahan pada telefon sebenar: NOT TESTED.** Jika `raw_stream` ditolak oleh server 4.0 pada peranti, fallback = framing mode (`send_frame_meta=true`) dengan probe diagnostik.

## ADR-003 — Kawalan input dikunci kepada device_id + validasi ketat
- Semua arahan melalui satu `DeviceControl` per serial; payload divalidasi (jenis, julat 0–1, panjang), kekunci hanya daripada senarai putih/integer, teks **tidak** pernah diinterpolasi ke shell (guna `input text` dengan aksara dilucutkan kepada set selamat, atau jalur `ime`/broadcast ditangguh; aksara di luar set ditolak dengan ralat jelas).
- Setiap arahan menyertakan `device_id` yang mesti sepadan dengan soket WS; dilog (audit) dengan device_id.

## ADR-004 — Perlindungan WebSocket/API lokal
- Server bind `127.0.0.1` sahaja (dikuatkuasakan dalam config, bukan hanya `desktop.py`).
- Token sesi rawak dijana pada setiap permulaan app dan dihantar kepada shell/UI; WS dan REST mutasi memerlukan token **dan** `Origin` yang dibenarkan. CORS `*` + credentials dihapuskan.

## ADR-005 — Data pengguna di `%APPDATA%\Mirrorhub`
- DB, log, upload, backup dipindahkan ke `%APPDATA%\Mirrorhub` (override `MIRRORHUB_DATA_DIR`). Migrasi: salin DB sedia ada **dengan backup**, tidak pernah padam. Arahan "delete mirrorhub.db" dibuang daripada dokumentasi.

## ADR-006 — Binari pihak ketiga
- `tools/scrcpy/` dikeluarkan daripada git; pemasang akan membundel binari hanya selepas semakan lesen (scrcpy Apache-2.0; ADB — Android SDK terms; FFmpeg — LGPL/GPL mengikut build; libusb LGPL-2.1; SDL3 zlib). Dokumen NOTICE akan disertakan.
