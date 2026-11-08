# KNOWN ISSUES (dikemas kini 2026-11-08)

| ID | Isu | Status |
|---|---|---|
| K1 | Shell injection `input text`/`keyevent` | **DIBETULKAN** (44 ujian). Pelari automasi lama (`automation_runner._type_text`) juga **dibetulkan** (ujian regresi) |
| K2 | WS tanpa Origin/token | **DIBETULKAN** |
| K3 | `screenrecord` ~180 s | **DIGANTI** oleh scrcpy raw stream — disahkan pada 2 telefon (HW) |
| K4 | FK `campaign_jobs.campaign_id` tidak dikuatkuasakan | **DIBETULKAN** untuk DB baharu; DB lama tiada FK (SQLite tidak boleh `ALTER` FK) → `delete_campaign` memadam job secara eksplisit |
| K5 | 30 ujian gagal | **SELESAI**: 16 diselesaikan (pembaikan kod: ADB path, FK, tz, load-balancer; ujian ditulis semula: mirror, queue, memory), 14 dikuarantin (skip + sebab) |
| K6 | DB dalam folder app / "delete mirrorhub.db" | **DIBETULKAN** (ADR-005); RELEASE_NOTES & CLAUDE.md dibetulkan |
| K7 | "Device Wall" bukan video | **DIBETULKAN** (HW: 2 telefon) |
| K8 | `host=0.0.0.0` | **DIBETULKAN** |
| K9 | `/ws/stream` (ejen Android) dan `/ws/view` (JPEG lama) tidak diaudit | Terbuka. Ejen Android tidak dibina/diuji; laluan lama tidak digunakan UI baharu |
| K10 | Port 8000 tetap | **DIBETULKAN** (desktop.py: lampirkan ke Mirrorhub sedia ada atau pilih port bebas) |
| K11 | Modul lanjutan (TikTok/YT/kandungan/kempen/AI) UI berlainan gaya (terang) dan liputan ujian ~11 % | Terbuka. Tidak termasuk dalam gate liputan teras (ADR-007); belum disahkan pada perkakasan |
| K12 | 14 ujian dikuarantin (agen/pemulihan/perancang) | Terbuka — tulis semula bila lapisan agen dipromosikan |
| K13 | Pemasang belum ditandatangani; SmartScreen akan memberi amaran | Terbuka (pemilik) |
| K14 | Semakan lesen redistribusi adb/FFmpeg belum rasmi | Terbuka (pemilik) — `packaging/THIRD_PARTY_NOTICES.txt` |
| K15 | Peranti USB kedua (`TSNF…`) kekal `offline` pada mesin pembangun | Isu telefon/kabel; dilaporkan dengan arahan oleh UI |
| K16 | Telefon yang sama pernah didaftar dengan IP:port lama (data lama) kekal sebagai entri "offline" berasingan sehingga dilupakan | Terbuka — gunakan *Lupakan*; tiada penggabungan automatik yang selamat |
| K17 | `wifi_ip` kosong pada Pixel (`wlan0` tiada) | Kosmetik |
| K18 | Penghentian proses skrip `asyncio.run` menunjukkan ResourceWarning "unclosed transport" pada Windows | Hanya skrip CLI; tiada kesan pada aplikasi |
| K19 | Input melalui `adb shell` berterusan: tiada pengakuan ralat per arahan (hanya kegagalan hantar) | Terbuka; kawalan melalui soket scrcpy ditangguh (ADR-002) |
| K20 | Hanya APK tunggal; `.apks/.xapk` tidak disokong; muat turun folder tidak disokong | Terbuka |
| K21 | Xiaomi/HyperOS menyekat input & pemasangan USB sehingga *USB debugging (Security settings)* / *Install via USB* dihidupkan | **Dikesan dan dilaporkan dalam UI** (`input_state`, mesej tile, mesej APK); tidak boleh dibaiki oleh aplikasi (tetapan keselamatan pemilik) |
| K22 | Peranti WiFi bersiri mDNS tidak disambung semula selepas terputus | **DIBETULKAN** (ditemui pada perkakasan 2026-11-08) |
| K23 | Kebocoran memori `permessage-deflate` pada setiap soket WS (~110 KB) | **DIBETULKAN** (ditemui melalui soak churn simulasi) |
| K24 | Soak telefon sebenar: banyak reconnect klien / soket video terputus | **DIBETULKAN** — punca: dua penulis serentak pada soket (`AssertionError` dalam `websockets._drain_helper`); penulis berkunci + ujian regresi; disahkan pada Pixel (0 reconnect dalam 25 + 16 min) |
| K25 | RSS bergerigi (≈ +5.5 MB/min hingga ≈ 270 MB) | **DIBETULKAN** — GC berkala 30 s; RSS rata (+4 MB / 16 min) |
| K26 | Menutup tetingkap ≈ 9 s (hos WebView2) | Terbuka, kosmetik |
| K27 | Ujian input dilakukan semasa pemilik/automasi menggunakan TikTok/Threads pada Pixel | Dinyatakan dalam laporan E2E; input dihentikan sebaik dikesan |
| K28 | Soket video diputuskan pada setiap keyframe besar (dua penulis serentak pada satu soket) | **DIBETULKAN** (V1.0.x, ujian regresi) |
| K29 | Pertumbuhan memori ≈ 5 MB/min (struktur ctypes per sampel, subproses asyncio per poll adb, tugas WS tidak di-await, fail reaper) | **DIBETULKAN di punca (V1.1)**; GC 5 min hanya jaring keselamatan; baki ≈ sampah SQLAlchemy daripada gelung modul lanjutan |
| K30 | "FPS rendah" palsu pada telefon idle (letusan keyframe awal / notifikasi singkat) | **DIBETULKAN (V1.1)** |
| K31 | Satu gangguan dikira 5 reconnect dan mencetus amaran gelung palsu | **DIBETULKAN (V1.1)** |
| K32 | Laporan diagnostik membocorkan IP apabila nama peranti = IP:port | **DIBETULKAN (V1.1)** |
| K33 | Statistik penyahkod pelayar: penulis terakhir menang jika beberapa pelayar membuka peranti sama | Terbuka (dinyatakan dalam dokumen dashboard) |
| K34 | Latency tap→bingkai tidak diukur | Terbuka |
| K35 | Sejarah prestasi hanya dalam memori (hilang bila aplikasi ditutup) | Terbuka |
| K36 | Bundle frontend > 500 KB (amaran Vite) | Terbuka, kosmetik |
| K38 | Rakaman skrin: fail MP4 tidak lengkap (3232 B, tanpa `moov`) kadangkala, terutama sebaik selepas pasang/nyahpasang APK — `screenrecord` tersekat ≈ 9 s dalam `fuse_simple_request` membuka fail di `/sdcard` lalu dihentikan sebelum bermula | **DIBETULKAN (V1.1)**: rakam ke `/data/local/tmp` (bukan FUSE), tunggu saiz stabil, sahkan `ftyp`+`moov`, jika tidak lengkap fail dibuang dan ralat jelas dipaparkan (bukan video rosak senyap). Disahkan 5/5 + 3/3 pada telefon sebenar dalam keadaan yang sebelum ini gagal 6/6 |
| K37 | Telefon dikunci tidak boleh dikawal/diuji (Mirrorhub tidak membuka kunci) | Dengan reka bentuk |
