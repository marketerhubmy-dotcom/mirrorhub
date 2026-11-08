# DECISIONS (ADR ringkas)

## ADR-001 — Shell desktop V1: kekalkan pywebview + FastAPI, tangguh Tauri
- **Konteks:** Plan §3 mencadangkan Tauri 2 "jika sesuai selepas audit". Audit: Rust/cargo tiada pada mesin ini; shell pywebview (`backend/desktop.py`) sudah wujud, WebView2 157 dipasang; backend Python ialah teras seluruh logik.
- **Keputusan:** V1 kekal pywebview + backend Python. Pakej dengan PyInstaller (onedir) + pemasang Inno Setup. Tauri dinilai semula selepas gate Release 1.0 (hanya jika ada keperluan konkrit: auto-update, tray, saiz).
- **Akibat:** tiada pemasangan Rust diperlukan; pemasang bergantung pada PyInstaller (pip, dalam venv) dan Inno Setup (pemasangan sistem — **perlu kelulusan pemilik**). Penyimpangan daripada plan ini sengaja dan direkodkan.

## ADR-002 — Embedded streaming: scrcpy-server `raw_stream` → WebSocket → WebCodecs
- **Konteks:** `adb screenrecord` ada had ~180 s, saiz tetap, tiada kawalan; tetingkap scrcpy berasingan tidak diterima (plan §1, rules #4).
- **Bukti:** `tools/scrcpy/scrcpy-win64-v4.0/scrcpy-server` (classes.dex) mengandungi pilihan `raw_stream`, `tunnel_forward`, `send_frame_meta`, `send_device_meta`, `send_dummy_byte`, `send_stream_meta`, `video_codec_options`, `max_size`, `max_fps`, `video_bit_rate`, `scid`. (Perhatian: `send_codec_meta` versi lama **tiada** → jangan andaikan protokol 3.x.)
- **Keputusan:** backend tolak `scrcpy-server` ke peranti, jalankan `app_process` dengan `raw_stream=true control=false audio=false tunnel_forward=true`, sambung melalui `adb forward` ke soket video, baca strim H.264 Annex-B mentah (tanpa framing), pisahkan NAL, kumpulkan kepada access unit (satu gambar = satu mesej WS; slice berbilang digabungkan), cache GOP terakhir (penonton lewat bermula pada keyframe), siar ke semua penonton WS dengan backpressure (penonton perlahan menunggu keyframe); pelayar nyahkod dengan WebCodecs ke `<canvas>`. Satu proses server per peranti (dikongsi antara penonton, thumbnail & fokus pada resolusi berbeza = sesi berasingan per profil).
- **Kenapa raw_stream:** menghapuskan risiko perubahan format framing antara versi scrcpy; cukup untuk video.
- **Kawalan:** laluan adb shell berterusan yang diperkuat (ADR-003). Kawalan melalui soket kawalan scrcpy ditangguh (perlu protokol 4.0 yang disahkan pada hardware).
- **Status:** kod + ujian unit terhadap strim sintetik. **Pengesahan pada telefon sebenar: NOT TESTED.** Jika `raw_stream` ditolak oleh server 4.0 pada peranti, fallback = framing mode (`send_frame_meta=true`) dengan probe diagnostik.

## ADR-003 — Kawalan input dikunci kepada device_id + validasi ketat (DILAKSANAKAN)
- Payload divalidasi (jenis, koordinat 0-1 terhingga, teks maks 500 tanpa aksara kawalan, keycode integer 0-400 atau `KEYCODE_*`, serial `[A-Za-z0-9._:-]`). Teks dipetik POSIX (petikan tunggal) sebelum ditaip ke shell berterusan; baris baharu ditolak. Ralat dinaikkan sebagai `ControlError` dan dibalas kepada klien (tidak lagi ditelan).
- Setiap mesej WS boleh membawa `device_id`; jika berbeza daripada soket, ditolak. Dilog audit (`mirrorhub.control.audit`).
- Had: `input text` Android tidak menyokong aksara bukan-ASCII; `%s` literal menjadi ruang.

## ADR-004 — Perlindungan WebSocket/API lokal (DILAKSANAKAN)
- Server bind `127.0.0.1` sahaja: `config.host` default ditukar daripada `0.0.0.0`; `effective_bind_host()` menolak antara muka bukan-loopback kecuali `ALLOW_REMOTE_BIND=true`.
- `LoopbackGuardMiddleware` (ASGI, merangkumi WS + REST): `Host` mesti loopback (anti DNS-rebinding); `Origin` untuk WS dan kaedah bukan-selamat mesti loopback atau disenaraikan dalam `CORS_ORIGINS`. CORS `*` + credentials dibuang.
- Token sesi **tidak** digunakan: ancaman sebenar ialah halaman web dalam pelayar pengguna; proses tempatan lain sudah boleh menjalankan `adb` sendiri. `/ws/stream` (ejen Android) tidak dilindungi Origin kerana klien bukan pelayar — diterima kerana Origin tiada = dibenarkan; ejen jauh memerlukan reka bentuk auth tersendiri (Fasa 07).

## ADR-005 — Data pengguna di `%APPDATA%\Mirrorhub` (DILAKSANAKAN)
- DB, log, upload, backup dipindahkan ke `%APPDATA%\Mirrorhub` (override `MIRRORHUB_DATA_DIR`). Migrasi: salin DB sedia ada **dengan backup**, tidak pernah padam. Arahan "delete mirrorhub.db" dibuang daripada dokumentasi.

## ADR-006 — Binari pihak ketiga
- `tools/scrcpy/` dikeluarkan daripada git; pemasang akan membundel binari hanya selepas semakan lesen (scrcpy Apache-2.0; ADB — Android SDK terms; FFmpeg — LGPL/GPL mengikut build; libusb LGPL-2.1; SDL3 zlib). Dokumen NOTICE akan disertakan.

## ADR-007 — Skop gate liputan: teras V1 (60 %), seluruh kod dilaporkan berasingan
- **Konteks:** 10.6k pernyataan; ~6.4k ialah modul pra-V1 (TikTok/YT, workflows, vision, content, campaign, orchestrator, agents) dengan liputan ~11 %. Mencapai 60 % merata memerlukan menguji jalur automasi UI aplikasi pihak ketiga yang tidak boleh disahkan tanpa akaun/telefon.
- **Keputusan:** gate `--cov-fail-under=60` dikira atas **teras V1** (`backend/.coveragerc` menyenaraikan pengecualian secara eksplisit). Angka seluruh kod dikira dengan `.coveragerc.all` dan dilaporkan dalam QA_MATRIX (46 %), bukan disembunyikan. Pengecualian tidak menambah liputan modul yang dikecualikan; ia hanya mengasingkan apa yang diperakui.
- **Akibat:** modul lanjutan kekal berisiko (K11). Memasukkannya semula ke gate ialah kerja berasingan.

## ADR-008 — Identiti peranti: nombor siri perkakasan
- `ro.serialno` menjadi kunci identiti (`devices.hw_serial`); `adb_address` ialah laluan semasa (USB diutamakan, WiFi sandaran). Satu telefon = satu baris walaupun USB dan WiFi serentak. `device_id` kekal `uuid5(DNS, adb_serial)` untuk rekod lama (serasi ke belakang) dan `uuid5(DNS, hw_serial)` untuk rekod baharu.
- Rekod lama tanpa `hw_serial` dipadankan melalui `adb_address`; nama pengguna tidak ditimpa.

## ADR-009 — Teras automasi umum berasingan daripada modul TikTok/YT
- `app/automation/core.py` (langkah tervalidasi, selari antara peranti, retry/timeout/batal, eksklusif per peranti, `Driver` boleh disuntik untuk ujian). Aktuasi hanya melalui `adb_control`/`device_ops` (tiada rentetan shell mentah). Modul lama dikekalkan di *Lanjutan* dan `automation_runner` dibaiki (injeksi teks).
