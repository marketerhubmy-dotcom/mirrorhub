# Laporan ujian hujung-ke-hujung: satu telefon (Pixel 6)

Tarikh: 2026-11-08 · Build: `Mirrorhub-Setup-1.0.0.exe` (SHA-256 dalam `dist/SHA256SUMS.txt`) · Peranti rujukan: **Pixel 6, Android 17, ADB WiFi (mDNS)**.
Aplikasi diuji **dalam keadaan dipasang** (dipasang ke `%LOCALAPPDATA%\Programs\Mirrorhub`, dilancarkan melalui pintasan Start Menu, data sebenar di `%APPDATA%\Mirrorhub`). UI dipandu melalui pelayar Chrome pada `http://127.0.0.1:8000` — frontend dan backend yang sama yang dihidangkan oleh `MirrorHub.exe` yang dipasang; tetingkap asli disahkan terbuka (tajuk "MirrorHub") tetapi dipandu melalui pelayar kerana automasi tetingkap WebView2 tidak tersedia.
Hanya tindakan tidak merosakkan: Home/Back/swipe/tap/taip teks ujian dalam bar alamat Chrome (tanpa Enter), fail ujian dalam folder sendiri (dipadam), pasang semula `-r` apl ujian pengguna, tangkapan skrin dan rakaman (dipadam). Tiada mesej, pembelian, pemadaman data atau perubahan tetapan keselamatan.

| # | Langkah | Hasil | Bukti |
|---|---|---|---|
| 1 | Install (senyap, lalai, pintasan Desktop) | **PASS** | exit 0; `MirrorHub.exe` v1.0.0, `adb.exe` & `scrcpy-server` ada; pintasan Start Menu + Desktop |
| 2 | Launch dari Start Menu | **PASS** | tetingkap "MirrorHub"; `/health` OK; backend bermula sendiri |
| 3 | Connect Pixel 6 (auto-detect) | **PASS** | muncul `online`, `input_state=ok`, wifi |
| 4 | Live mirror (Device Wall) | **PASS** | kanvas 432×960 dinyahkod, 99 % piksel bukan-hitam; selepas reconnect strim hidup semula (perubahan skrin dikesan) |
| 5 | Tap | **PASS** | tap pada bar alamat Chrome dipetakan tepat (`url_bar focused=true`) |
| 6 | Swipe | **PASS** | swipe dari atas: skrin berubah (diff 72.7); Back memulihkan |
| 7 | Type | **PASS** | "e2e install test" tiba utuh dalam `url_bar` |
| 8 | Home / Back | **PASS** | Home dari apl lain → Launcher (`topResumedActivity`) |
| 9 | Screenshot | **PASS** | PNG sah 2.9 MB |
| 10 | Screen recording | **PASS** | MP4 sah (`ftyp`+`moov`) |
| 11 | File transfer | **PASS** | 8 MB rawak + nama berspasi: muat naik → muat turun → SHA-256 sama; folder ujian dipadam |
| 12 | Install APK | **PASS** | `-r` apl ujian pengguna, "Berjaya dipasang." |
| 13 | Automation core (baca sahaja) | **PASS** | 3/3 langkah (tunggu, tangkap skrin, uiautomator) |
| 14 | Reconnect | **PASS** | `adb reconnect` pada laluan mDNS → `reconnecting` → `online` dalam ≈ 8 s; laluan bertukar ke IP:port secara automatik |
| 15 | Close | **PASS** | WM_CLOSE → proses keluar, port 8000 bebas |
| 16 | Relaunch | **PASS** | peranti dikesan semula `online` sendiri |
| 17 | Settings persistence | **PASS** | nama/kumpulan/tag peranti dan keutamaan (`wall_layout=1`, `record_seconds=30`, kualiti) kekal; butang susun atur "1" aktif selepas buka semula |
| 18 | UI tanpa ralat | **PASS** | 8 halaman dimuat, 0 ralat konsol/penolakan |

## Pepijat penghalang ditemui dan dibaiki dalam sesi ini
1. **Gelung reconnect / soket video terputus** — `send_video` dan `send_status` menulis serentak pada soket yang sama; `websockets` menegaskan satu penulis semasa aliran tersekat (`AssertionError`) → soket putus pada setiap keyframe besar (≈ 100 putus/saat dalam ujian terpencil; punca K24). Dibaiki dengan penulis berkunci; ujian regresi gagal tanpa pembaikan dan lulus dengan pembaikan; pada Pixel: 0 putus dalam 40 s, soak 4 min 0 reconnect.
2. **Kebocoran memori `permessage-deflate`** (110 KB/soket) — dimatikan.
3. **Peranti mDNS tidak disambung semula** — dibaiki (resolusi mDNS).
4. **Input disekat OEM tidak dilaporkan** — dikesan dan dipaparkan.
5. **Tetapan WebView2 tidak kekal** (`private_mode` lalai) — `private_mode=False` + `storage_path`.

## Pemerhatian jujur
- Semasa ujian, Pixel digunakan oleh pemilik/automasi di luar Mirrorhub (aplikasi Threads dan TikTok `SparkActivity` muncul di latar depan). Beberapa Home/Back/swipe saya berselang-seli dengan penggunaan itu; selepas itu input dihentikan. Sila semak TikTok anda tiada sesi yang terganggu.
- Menutup tetingkap mengambil ≈ 10 s (kini dihadkan 3 s untuk penutupan soket; belum diukur semula pada build akhir — lihat laporan akhir).
- Tetingkap aplikasi yang dipasang tidak dipandu secara automatik (sama backend/frontend, dipandu melalui Chrome).
