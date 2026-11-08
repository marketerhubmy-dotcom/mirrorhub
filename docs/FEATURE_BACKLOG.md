# FEATURE BACKLOG (ikut keutamaan) — dikemas kini 2026-11-09

## Siap
**V1.0 (Single Device Ready)** — strim embedded + Device Wall, kawalan terikat `device_id`, loopback-only, data AppData + backup, Pairing Center, Device Manager, APK/Fail, automasi umum, reconnect/pemulihan, pemasang, tetapan kekal.
**V1.1 (branch `dev/performance-v1.1`)** — Performance Dashboard (kad, 8 graf, jadual per peranti, kesihatan, amaran dengan hysteresis/cooldown, log peristiwa, eksport JSON/CSV/teks tanpa rahsia, ambang boleh dikonfigurasi); instrumentasi strim (resolusi SPS, bingkai dihantar/digugurkan, masa mula, reconnect); statistik penyahkod pelayar; ujian pengasingan multi-device; pembaikan kebocoran punca (ctypes per-sampel, subproses adb asyncio, tugas WS dibatalkan tanpa await, reaper); versi 1.1.0.

## P0 — seterusnya (V1.2 / MULTI_DEVICE_READY)
- [ ] Ujian perkakasan 4+ telefon berperingkat (2 → 4 → 9) dengan `app.tools.soak` dan halaman Prestasi
- [ ] Soak 8 jam pada telefon sebenar (rekod baseline/akhir dalam laporan)
- [ ] Ujian cabut kabel USB, WiFi telefon off, reboot (perlu tindakan/kebenaran pemilik)
- [ ] Input + APK pada Redmi (perlu "USB debugging (Security settings)" / "Install via USB")
- [ ] Latency hujung-ke-hujung (tap → bingkai) dalam dashboard
- [ ] Pemasang pada Windows bersih; tandatangan kod; semakan lesen adb/FFmpeg
- [ ] Kawalan input melalui soket scrcpy (menggantikan `adb shell input`)

## P1 — Release 1.5: Virtual Android (perlu JDK + Android SDK + WHPX; belum dimulakan)
## P2 — Release 2.0–3.1: Remote connector, cloud virtual, billing (perlu kelulusan pemilik)

## Idea kecil (tidak dijadualkan)
- Sejarah prestasi dikekalkan ke cakera (kini dalam memori sahaja)
- Pemisahan kod modul lanjutan (TikTok/YT/AI) daripada teras supaya liputan merangkumi semuanya
- Pecah bundle frontend (>500 KB) dengan pemuatan malas per halaman
