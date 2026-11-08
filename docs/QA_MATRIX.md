# QA MATRIX

Persekitaran ujian: Windows 11 (10.0.26200), Ryzen 5 7535HS, 23.2 GB RAM, mesin pembangun (ada Python/Node/Rust-tiada). Telefon fizikal tersedia pada **2026-11-08**: Pixel 6 (Android 17, ADB WiFi/mDNS), Redmi 24094RAD4G (Android 16, USB); satu entri USB ketiga kekal `offline`.
Legenda: PASS / FAIL / NOT TESTED. **PASS (HW)** = telefon sebenar. **PASS (sim)** = simulasi/unit/integrasi — bukan bukti perkakasan.

| # | Kategori | Item | Status | Bukti | Tarikh |
|---|---|---|---|---|---|
| 1 | Build | Frontend `tsc --noEmit` | PASS | 0 ralat | 2026-11-08 |
| 2 | Build | Frontend `npm run build` | PASS | ~490 kB JS | 2026-11-08 |
| 3 | Unit/Integrasi | Backend pytest | **PASS** | **465 lulus, 0 gagal, 14 dikuarantin dengan sebab** (`TEST_QUARANTINE.md`) | 2026-11-08 |
| 3a | Coverage | Gate ≥ 60 % (skop teras V1, ADR-007) | **PASS 72.9 %** | `backend/.coveragerc` | 2026-11-08 |
| 3b | Coverage | Seluruh kod (tanpa pengecualian) | 46.0 % (maklumat, tiada gate) | `--cov-config=.coveragerc.all` | 2026-11-08 |
| 4 | Device | `adb devices` mengesan telefon | **PASS (HW)** | 3 entri; 2 `device`, 1 `offline` dilaporkan dengan arahan | 2026-11-08 |
| 4a | Device | Maklumat peranti (model/Android/bateri/storan/skrin) | **PASS (HW)** | Pixel 6 & Redmi; `docs/HWCHECK_SAMPLE_2026-11-08.md` | 2026-11-08 |
| 4b | Device | Pendaftaran automatik + identiti USB/WiFi (hw serial) | PASS (sim) + PASS (HW: daftar & offline-startup) | `test_device_lifecycle.py` 16 ujian; run sebenar | 2026-11-08 |
| 5 | Device | 4+ telefon, tiada input silang | **BLOCKED / separa** | hanya 2 telefon; input Redmi disekat (B1). Log audit: perintah Pixel hanya ke Pixel (`HARDWARE_VALIDATION.md` P4, B2, B4) | 2026-11-08 |
| 6 | Streaming | Dua strim embedded dalam satu UI, telefon sebenar | **PASS (HW)** | 2 telefon serentak; bingkai pertama 1.1/2.7 s; 2 kanvas Chrome berisi piksel sebenar | 2026-11-08 |
| 6a | Streaming | Nyahkod pelayar Annex-B, slice berbilang | PASS (sim) | `backend/tests/sim/` | 2026-11-08 |
| 6b | Input | Klik/tap/swipe/taip/Home/Back melalui Device Wall, terikat device_id | **PASS (HW) pada Pixel · BLOCKED pada Redmi** | P4; Redmi: `INJECT_EVENTS` (tetapan keselamatan Xiaomi, tidak diubah) — B1 | 2026-11-08 |
| 6c | Security | Suntikan shell, Origin lintas-tapak, DNS rebinding | PASS (unit+aplikasi penuh) | 78 + smoke app sebenar (403/4403) | 2026-11-08 |
| 7 | Streaming | FPS/latency/CPU | **Separa (HW)** | Pixel: 10.2 fps @ 803 kbit/s pada skrin bergerak, CPU backend 0.06 s/8 s. Latency hujung-ke-hujung & 4+ telefon NOT TESTED (H3/H4) | 2026-11-08 |
| 8 | Reliability | Hot-plug / WiFi putus / adb server mati / reconnect | **PASS (HW): adb server mati → pulih ≈7 s; `adb reconnect` → pulih ≈8 s; putus manual tidak dicetus semula; 2 laluan = 1 peranti**. Cabut kabel fizikal, WiFi telefon off, reboot: BLOCKED/NOT TESTED | P5–P9, B5, B7 | 2026-11-08 |
| 8a | Reliability | Unauthorized dilaporkan | PASS (sim) · entri `unauthorized` sebenar dipaparkan; kitaran Allow NOT TESTED (N2) | | 2026-11-08 |
| 9 | Installer | Pasang/nyahpasang/kemas kini | **PASS (mesin pembangun) 18/18** | `packaging/smoke_installer.ps1`, `build/installer-smoke.json` | 2026-11-08 |
| 9a | Installer | Windows bersih tanpa Python/Node | **BLOCKED**: Windows Home (tiada Sandbox/VM). Separa: smoke 19/19 dengan profil terpencil (APPDATA/TEMP/PATH baharu, tiada Python/Node) | B8 | 2026-11-08 |
| 9b | Installer | Tandatangan kod | NOT DONE | pemilik | — |
| 10 | Stability | Soak 8 jam | **NOT TESTED (HW)** — telefon terputus; soak simulasi 8+3+2+3 min menemui dan membetulkan kebocoran deflate (RSS stabil, thread/handle stabil) | B6 | 2026-11-08 |
| 11 | Database | Migrasi AppData + backup + restore berperingkat | PASS (unit 14 + API) | `test_data_migration.py`, smoke app | 2026-11-08 |
| 11a | Database | Migrasi data pengguna sebenar (`backend\mirrorhub.db` → AppData) | **PASS (HW-data)** | disalin, integrity_check ok, sumber tidak disentuh; 9 baris peranti terbawa | 2026-11-08 |
| 12 | Automation | Enjin: urutan, retry, timeout, batal, selari, eksklusif | PASS (sim) 45 ujian | `test_automation_core.py`, `test_automation_api.py` | 2026-11-08 |
| 12a | Automation | wait + screenshot + uiautomator dump (baca sahaja) | **PASS (HW)** | 2 telefon | 2026-11-08 |
| 12b | Automation | Langkah yang menggerakkan telefon | **PASS (HW) pada Pixel** melalui Wall (tap/swipe/taip/nav); enjin automasi sendiri belum menjalankan langkah input pada telefon · Redmi BLOCKED | P4 | 2026-11-08 |
| 13 | APK/Fail | Senarai pakej, senarai fail, tangkap skrin | **PASS (HW)** | 40/51 pakej, 8/20 folder, PNG sah | 2026-11-08 |
| 13a | APK/Fail | Pasang APK, muat naik/turun, rakam skrin | **PASS (HW)**: -r pada Pixel; fail 200 MB SHA-256 sama (kedua-dua); MP4 sah. Pasang baharu pada Redmi **BLOCKED** (Install via USB) | P10–P14, B3 | 2026-11-08 |
| 14 | Pairing | Pair/connect/discover WiFi | PASS (sim: validasi + tafsiran) · telefon sudah ada sambungan mDNS, **pairing baharu NOT TESTED** | H12 | — |
| 15 | Virtual | 2 emulator | NOT TESTED | tiada Android SDK/JDK | — |
| 16 | Remote/Cloud/Billing/Ops | semua | NOT TESTED / tidak dimulakan | di luar skop V1 | — |

## Kemas kini 2026-11-08 (keluaran satu telefon)
| # | Item | Status | Bukti |
|---|---|---|---|
| S1 | E2E dalam aplikasi dipasang: install → launch → connect → mirror → tap → swipe → type → screenshot → rakam → fail → APK → automasi → reconnect → tutup → buka semula → tetapan kekal | **PASS (HW, Pixel 6) 18/18** | `docs/E2E_SINGLE_DEVICE_REPORT.md` |
| S2 | Soak telefon sebenar (aplikasi dipasang) 25 min + 16 min, 1 telefon | **PASS** (0 reconnect/ralat; RSS rata selepas GC) — **bukan** soak 8 jam | `soak_installed*.log` |
| S3 | Kemas kini pemasang di atas aplikasi berjalan | **PASS** | hash binari sama, data utuh |
| S4 | SINGLE_DEVICE_READY | **YA** | `RELEASE.md` |
| S5 | MULTI_DEVICE_READY | **TIDAK (belum diuji)** | `HARDWARE_VALIDATION.md` |


## V1.1 (2026-11-09)
| # | Item | Status | Bukti |
|---|---|---|---|
| P1 | Backend pytest | **PASS 553 lulus, 0 gagal, 14 dikuarantin** | liputan teras **79.1 %** (gate 60 %); seluruh kod **52.2 %** (maklumat, tanpa pengecualian) |
| P2 | Frontend `tsc`, `vite build`, **vitest 13 ujian** | **PASS** | dijalankan oleh `packaging\build.ps1` |
| P3 | Dashboard: metrik sebenar, graf, jadual per peranti, kesihatan, amaran, peristiwa, eksport | **PASS (HW 2 Pixel)** | `HARDWARE_VALIDATION.md` V3–V9 |
| P4 | Pengasingan multi-device (perisian) | PASS | `test_multidevice_isolation.py` (8) + `test_perf.py` (55) |
| P5 | Pengasingan input dua telefon (perkakasan) | **PASS (HW 2 Pixel)** | V1 |
| P6 | Tiada reconnect loop / kebocoran kritikal dalam ujian yang dijalankan | **PASS (terhad)**: 30 min dipasang (RSS +4.9 MB), 12 min, 9-peranti simulasi 8 min | V11–V12; **bukan soak 8 jam** |
| P7 | Soak 8 jam | **NOT TESTED** | — |
| P8 | Pemasang 1.1.0: build, smoke 19/19 (normal), 20/20 (profil terpencil), kemas kini dari 1.0.0 | **PASS (mesin pembangun)** | `packaging\smoke_installer.ps1` |
| P9 | Windows bersih | **BLOCKED** | Windows Home |
| P10 | MULTI_DEVICE_READY | **TIDAK** (4+ telefon, 8 j, USB/WiFi fizikal belum diuji) | — |
| P11 | Regresi satu telefon pada aplikasi dipasang (screenshot, fail SHA, APK, rakaman, automasi) | **PASS (HW Pixel 6) 3/3 larian** selepas pembetulan K38 (rakaman sebelum ini flaky) | `HARDWARE_VALIDATION.md` V15–V16 |
