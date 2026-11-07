# QA MATRIX

Persekitaran: Windows 11 (10.0.26200), Ryzen 5 7535HS, 23.2 GB RAM. **Telefon fizikal diuji: 0.**
Legenda: PASS / FAIL / NOT TESTED. Mock/unit ≠ bukti hardware.

| # | Kategori | Item | Status | Bukti / sebab | Tarikh |
|---|---|---|---|---|---|
| 1 | Build | Frontend `tsc --noEmit` | PASS | 0 error | 2026-11-08 |
| 2 | Build | Frontend `npm run build` | PASS | 76 modul, built 1.87 s | 2026-11-08 |
| 3 | Unit | Backend pytest (baseline) | **FAIL** | 106 pass / 30 fail; coverage 14% < 60% | 2026-11-08 |
| 4 | Device | `adb devices` mengesan ≥1 telefon | NOT TESTED | 0 peranti disambung | 2026-11-08 |
| 5 | Device | 4 fizikal, 2 stream aktif, tiada cross-device input | NOT TESTED | tiada hardware | — |
| 6 | Streaming | Dua stream embedded dalam satu UI (PoC gate) | NOT TESTED | kod ditulis, tiada telefon | — |
| 7 | Streaming | FPS/CPU/RAM/latency | NOT TESTED | — | — |
| 8 | Reliability | USB cabut / WiFi putus / reboot / unauthorized | NOT TESTED | — | — |
| 9 | Installer | Pasang pada Windows bersih / update / uninstall | NOT TESTED | pemasang belum dibina | — |
| 10 | Stability | Soak 8 jam | NOT TESTED | — | — |
| 11 | Database | Migrasi + backup/restore | NOT TESTED | — | — |
| 12 | Automation | Workflow pada 2 peranti, cancel/retry | NOT TESTED | — | — |
| 13 | Virtual | 2 emulator serentak | NOT TESTED | Tiada Android SDK/Java | — |
| 14 | Remote/Cloud/Billing/Ops | semua | NOT TESTED | di luar skop lokal V1 | — |

(Jadual dikemas kini selepas setiap milestone.)
