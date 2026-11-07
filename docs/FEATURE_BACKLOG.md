# FEATURE BACKLOG (ikut keutamaan)

P0 — Release 1.0 (Fasa 00–05)
- [ ] Embedded stream per peranti (scrcpy raw_stream) + Device Wall grid 1/2/4/9 + Focus Mode
- [ ] Kawalan input terikat device_id (validasi, audit)
- [ ] Token sesi + Origin check; loopback-only; buang CORS `*`
- [ ] Data di `%APPDATA%\Mirrorhub`; migrasi dengan backup
- [ ] Pairing UI: USB hot-plug, WiFi pairing code (`adb pair`), keadaan authorized/unauthorized/offline
- [ ] Device manager: rename, tags, group, battery/storage/version
- [ ] APK install/uninstall, push/pull, screenshot, screen recording
- [ ] Reconnect/recovery tanpa crash peranti lain
- [ ] Automation core umum (bukan TikTok sahaja) + queue persisten, cancel/retry
- [ ] Pembersihan 30 ujian gagal (kemas kini ujian lapuk, betulkan FK)
- [ ] Pemasang `.exe` (PyInstaller + Inno Setup), semakan lesen, NOTICE
- [ ] Buang/label mock; UI halaman TikTok/AI dijadikan modul pilihan

P1 — Release 1.5: Virtual Android (perlu JDK + Android SDK + WHPX diagnosis)
P2 — Release 2.0–3.1: Remote connector, cloud virtual, billing (perlu kelulusan & akses pemilik)
