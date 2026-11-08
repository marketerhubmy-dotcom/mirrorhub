# Performance Dashboard (V1.1)

Halaman **Prestasi** dalam sidebar. Semua angka diukur; jika sesuatu tidak dapat diukur ia dipaparkan **N/A** dengan sebabnya (tooltip / teks). Tiada metrik direka.

## 1. Apa yang diukur dan bagaimana
| Metrik | Sumber | Catatan |
|---|---|---|
| CPU PC (%) | `GetSystemTimes` (delta antara dua sampel) | Seluruh PC. Sampel pertama = N/A (perlu dua bacaan) |
| RAM PC (used/total, %) | `GlobalMemoryStatusEx` | Seluruh PC |
| CPU proses Mirrorhub (%) | `time.process_time` delta ÷ masa dinding ÷ bilangan CPU logik | Hanya proses backend (termasuk tetingkap pywebview). `adb.exe` dan proses WebView2 tidak termasuk — dikira Windows secara berasingan |
| RAM proses (RSS), thread, handle | `GetProcessMemoryInfo`, `GetProcessHandleCount` | |
| Strim aktif | sesi `StreamManager` dalam keadaan `streaming` | |
| FPS strim | delta bilangan gambar dihantar hub ÷ masa; purata bergolek ±30 s | Hanya strim **aktif** dimasukkan dalam purata keseluruhan |
| Bitrate | delta bait H.264 dihantar hub ÷ masa | bait strim video sebenar |
| Resolusi | SPS H.264 dihuraikan (disahkan: Pixel 6 → 432×960 sepadan kanvas pelayar) | |
| Masa mula strim | permintaan sesi pertama → bingkai pertama | |
| Reconnect | pertukaran sesi ke `reconnecting`, dicatat per peranti dan keseluruhan (5 min/15 min/1 jam) | |
| WebSocket | pengira terbuka mengikut jenis (video/control/devices), sentiasa seimbang walaupun ralat | |
| Bingkai dihantar / digugurkan (server) | kaunter hub; gugur = penonton perlahan menunggu keyframe | |
| Bingkai diterima / dinyahkod / digugurkan (pelayar) | tile Device Wall melapor setiap 5 s (`POST /perf/client-stats`) | N/A jika tiada tile terbuka; laporan > 20 s dianggap lapuk |
| Bateri, storan | daftar peranti (dibaca daripada telefon) | N/A jika offline |

## 2. Idle bukan rosak
Skrin telefon yang statik menyebabkan scrcpy hampir tidak menghantar bingkai. Maka:
- **Aktiviti** dinilai daripada kadar bait **~6 s terkini** (≥ 15 KB/s = *active*, kurang = *idle*) — bukan daripada FPS.
- **10 s pertama** selepas bingkai pertama = *warmup* (letupan keyframe awal tidak dinilai).
- FPS rendah hanya dikira sebagai masalah apabila strim **aktif berterusan ≥ 3 sampel (±6 s)** dan FPS terkini < ambang. Letusan pendek (notifikasi) tidak.
- Graf FPS menunjukkan **jurang** (N/A) apabila semua strim idle, bukan sifar palsu.

## 3. Status kesihatan (per peranti)
| Status | Maksud |
|---|---|
| **Sihat** | Online; tiada strim, atau strim lancar / idle / sedang bermula |
| **Terjejas** | FPS rendah semasa skrin aktif berterusan; ≥ N reconnect dalam tetingkap (gelung); strim lambat bermula; strim `failed`; belum bermula > 30 s |
| **Menyambung semula** | peranti `reconnecting`, atau sesi strim `reconnecting` |
| **Terputus** | offline / tiada sambungan |
| **Perlu kebenaran** | `unauthorized` — telefon belum menekan Allow |
Kesihatan sistem = *Perlu perhatian* jika ada amaran aktif atau peranti terjejas.

## 4. Ambang (boleh diubah: butang **Ambang**, disimpan dalam `preferences.json`)
| Kunci | Lalai | Fungsi |
|---|---|---|
| `perf_ram_high_pct` | 90 | amaran RAM PC (pulih di bawah nilai − 5) |
| `perf_cpu_high_pct` / `perf_cpu_sustain_s` | 90 / 30 | CPU PC berterusan (pulih di bawah nilai − 15) |
| `perf_fps_low` | 5 | FPS minimum untuk strim aktif |
| `perf_reconnect_loop_count` / `perf_reconnect_window_s` | 5 / 120 | gelung reconnect |
| `perf_startup_slow_s` | 10 | strim lambat bermula |
| `perf_max_streams` | 8 | had strim aktif |
| `perf_rss_growth_mb` | 150 | pertumbuhan memori proses dalam ≤ 10 min |
| `perf_alert_cooldown_s` / `perf_alerts_enabled` | 300 / true | cooldown dan notifikasi |

## 5. Amaran
RAM tinggi · CPU tinggi berterusan · gelung reconnect · strim tersangkut (`failed`, `reconnecting` > 60 s, `starting` > 45 s) · pertumbuhan memori proses · terlalu banyak strim.
**Hysteresis:** amaran dicetus selepas beberapa sampel berturut-turut dan pulih hanya selepas beberapa sampel di bawah ambang yang lebih rendah (jalur antara keduanya mengekalkan keadaan). **Cooldown:** pencetusan semula dalam tempoh cooldown kekal aktif tetapi senyap. Amaran dihantar ke UI melalui `/ws/devices` (toast) dan direkod dalam log peristiwa.

## 6. Retensi dan beban
- Sampel setiap 2 s: cincin 1 jam (1 800) + agregat 30 s selama 24 jam (2 880); log peristiwa 1 000 entri; sejarah amaran 200; laporan klien ≤ 256 peranti. Semuanya berhad.
- Graf dikecilkan (downsampled) kepada ≤ 240 titik; kiraan reconnect dijumlahkan dalam baldi, bukan dipurata.
- Halaman hanya membuat polling apabila tab kelihatan (2 s ringkasan/peranti, 5 s sejarah/peristiwa) dan berhenti apabila ditinggalkan.
- Pengumpul: satu tick 2 s, tanpa subproses dan tanpa DB (kiraan peranti DB setiap 10 s).

## 7. Diagnostik
- **Salin laporan** (teks), **Eksport JSON**, **CSV** (sejarah, peranti, peristiwa).
- Laporan mengandungi: versi, OS, ringkasan, kad, ambang, amaran, jadual peranti + ringkasan punca dalam bahasa mudah, 200 peristiwa terkini, 5 minit sejarah, hasil diagnostik persekitaran.
- **Tidak** mengandungi: pembolehubah persekitaran, kunci API, kandungan skrin atau fail. Alamat IP disembunyikan (`192.168.x.x`), nombor siri mDNS dipendekkan, nama pengguna Windows dalam laluan → `<user>`, rentetan kunci/kata laluan → `[redacted]`, `device_id` dipendekkan. `?identifiers=true` (API sahaja) mengekalkan pengecam.

## 8. API
`GET /api/v1/perf/overview | history?range=5m|15m|1h|session | devices | events | alerts | thresholds | diagnostics | diagnostics.txt | export.csv?kind=` · `PUT /perf/thresholds` · `POST /perf/client-stats`.

## 9. Had yang diketahui
- Proses WebView2 dan `adb.exe` tidak termasuk dalam "proses Mirrorhub".
- Statistik penyahkod pelayar ialah laporan tile terakhir (jika beberapa pelayar membuka peranti yang sama, penulis terakhir menang).
- Latency tap→bingkai tidak diukur (belum ada instrumentasi hujung-ke-hujung).
- Sejarah ada dalam memori sahaja; hilang apabila aplikasi ditutup (peristiwa penting juga ada dalam `logs\mirrorhub.log`).
