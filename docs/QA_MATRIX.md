# QA MATRIX

Persekitaran ujian: Windows 11 (10.0.26200), Ryzen 5 7535HS, 23.2 GB RAM, mesin pembangun (ada Python/Node/Rust-tiada). Telefon fizikal tersedia pada **2026-11-08**: Pixel 6 (Android 17, ADB WiFi/mDNS), Redmi 24094RAD4G (Android 16, USB); satu entri USB ketiga kekal `offline`.
Legenda: PASS / FAIL / NOT TESTED. **PASS (HW)** = telefon sebenar. **PASS (sim)** = simulasi/unit/integrasi — bukan bukti perkakasan.

| # | Kategori | Item | Status | Bukti | Tarikh |
|---|---|---|---|---|---|
| 1 | Build | Frontend `tsc --noEmit` | PASS | 0 ralat | 2026-11-08 |
| 2 | Build | Frontend `npm run build` | PASS | ~490 kB JS | 2026-11-08 |
| 3 | Unit/Integrasi | Backend pytest | **PASS** | **457 lulus, 0 gagal, 14 dikuarantin dengan sebab** (`TEST_QUARANTINE.md`) | 2026-11-08 |
| 3a | Coverage | Gate ≥ 60 % (skop teras V1, ADR-007) | **PASS 75.3 %** | `backend/.coveragerc` | 2026-11-08 |
| 3b | Coverage | Seluruh kod (tanpa pengecualian) | 46.0 % (maklumat, tiada gate) | `--cov-config=.coveragerc.all` | 2026-11-08 |
| 4 | Device | `adb devices` mengesan telefon | **PASS (HW)** | 3 entri; 2 `device`, 1 `offline` dilaporkan dengan arahan | 2026-11-08 |
| 4a | Device | Maklumat peranti (model/Android/bateri/storan/skrin) | **PASS (HW)** | Pixel 6 & Redmi; `docs/HWCHECK_SAMPLE_2026-11-08.md` | 2026-11-08 |
| 4b | Device | Pendaftaran automatik + identiti USB/WiFi (hw serial) | PASS (sim) + PASS (HW: daftar & offline-startup) | `test_device_lifecycle.py` 16 ujian; run sebenar | 2026-11-08 |
| 5 | Device | 4+ telefon, 2 strim aktif, tiada input silang | NOT TESTED | hanya 2 telefon; input belum diuji (H2/H4) | — |
| 6 | Streaming | Dua strim embedded dalam satu UI, telefon sebenar | **PASS (HW)** | 2 telefon serentak; bingkai pertama 1.1/2.7 s; 2 kanvas Chrome berisi piksel sebenar | 2026-11-08 |
| 6a | Streaming | Nyahkod pelayar Annex-B, slice berbilang | PASS (sim) | `backend/tests/sim/` | 2026-11-08 |
| 6b | Input | Klik→tap dipetakan dan terikat device_id | PASS (sim) | log harness; unit `check_binding`; **HW: NOT TESTED** | 2026-11-08 |
| 6c | Security | Suntikan shell, Origin lintas-tapak, DNS rebinding | PASS (unit+aplikasi penuh) | 78 + smoke app sebenar (403/4403) | 2026-11-08 |
| 7 | Streaming | FPS/latency/CPU | **Separa (HW)** | Pixel: 10.2 fps @ 803 kbit/s pada skrin bergerak, CPU backend 0.06 s/8 s. Latency hujung-ke-hujung & 4+ telefon NOT TESTED (H3/H4) | 2026-11-08 |
| 8 | Reliability | Cabut USB / WiFi putus / reboot | PASS (sim: state machine, reconnect, outage adb) · **HW NOT TESTED** | `test_device_lifecycle.py` (H5–H8) | — |
| 8a | Reliability | Unauthorized dilaporkan | PASS (sim) | HW NOT TESTED (H8) | — |
| 9 | Installer | Pasang/nyahpasang/kemas kini | **PASS (mesin pembangun) 18/18** | `packaging/smoke_installer.ps1`, `build/installer-smoke.json` | 2026-11-08 |
| 9a | Installer | Windows bersih tanpa Python/Node | NOT TESTED pada VM bersih. Separa: exe beku lulus selftest dengan PATH hanya System32 (2026-11-08) | H15 | — |
| 9b | Installer | Tandatangan kod | NOT DONE | pemilik | — |
| 10 | Stability | Soak 8 jam | NOT TESTED | H13 | — |
| 11 | Database | Migrasi AppData + backup + restore berperingkat | PASS (unit 14 + API) | `test_data_migration.py`, smoke app | 2026-11-08 |
| 11a | Database | Migrasi data pengguna sebenar (`backend\mirrorhub.db` → AppData) | **PASS (HW-data)** | disalin, integrity_check ok, sumber tidak disentuh; 9 baris peranti terbawa | 2026-11-08 |
| 12 | Automation | Enjin: urutan, retry, timeout, batal, selari, eksklusif | PASS (sim) 45 ujian | `test_automation_core.py`, `test_automation_api.py` | 2026-11-08 |
| 12a | Automation | wait + screenshot + uiautomator dump (baca sahaja) | **PASS (HW)** | 2 telefon | 2026-11-08 |
| 12b | Automation | Langkah menggerakkan telefon (ketik/taip/buka apl) | NOT TESTED | H1 | — |
| 13 | APK/Fail | Senarai pakej, senarai fail, tangkap skrin | **PASS (HW)** | 40/51 pakej, 8/20 folder, PNG sah | 2026-11-08 |
| 13a | APK/Fail | Pasang APK, muat naik/turun, padam, rakam skrin | PASS (sim: arahan, validasi, penghalaan) · **HW NOT TESTED** | `test_device_ops.py`, `test_device_api.py` (H9–H11) | — |
| 14 | Pairing | Pair/connect/discover WiFi | PASS (sim: validasi + tafsiran) · telefon sudah ada sambungan mDNS, **pairing baharu NOT TESTED** | H12 | — |
| 15 | Virtual | 2 emulator | NOT TESTED | tiada Android SDK/JDK | — |
| 16 | Remote/Cloud/Billing/Ops | semua | NOT TESTED / tidak dimulakan | di luar skop V1 | — |
