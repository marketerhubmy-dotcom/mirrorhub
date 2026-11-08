# RELEASE

## Artifak (Desktop V1, 1.0.0)
| Fail | Keterangan |
|---|---|
| `dist/Mirrorhub-Setup-1.0.0.exe` | Pemasang Windows x64, per-pengguna, tanpa admin. SHA-256 dalam `dist/SHA256SUMS.txt` |
| `build/pyi-dist/MirrorHub/` | Folder portable (PyInstaller onedir + `tools/`) — boleh dijalankan terus `MirrorHub.exe` |
`dist/` dan `build/` tidak dikomit (dijana). Binari pihak ketiga (`tools/`) tidak dalam git (ADR-006); pemasang membundelnya.

## Bina semula
```powershell
powershell -ExecutionPolicy Bypass -File packaging\build.ps1            # ujian backend → build UI → PyInstaller → selftest exe → Inno Setup
powershell -ExecutionPolicy Bypass -File packaging\smoke_installer.ps1  # pasang senyap → verifikasi → buka tetingkap → nyahpasang
```
Prasyarat pembangun sahaja: Python venv `backend\.venv` (+ `pip install -r requirements.txt pyinstaller`), Node, Inno Setup 6 (`winget install JRSoftware.InnoSetup`). Pengguna akhir tidak memerlukan satu pun.

## Pasang / kemas kini / nyahpasang
- Pasang: jalankan `.exe`. Kemas kini: jalankan pemasang versi lebih baharu di atas yang lama (AppId sama; adb dihentikan dahulu). Data di `%APPDATA%\Mirrorhub` tidak disentuh; skema DB dinaik taraf automatik selepas backup.
- Nyahpasang: *Apps & features* atau `unins000.exe`. Data pengguna kekal.
- Senyap: `Mirrorhub-Setup-1.0.0.exe /VERYSILENT /SUPPRESSMSGBOXES /CURRENTUSER`.

## Data & rollback
- Lokasi: `%APPDATA%\Mirrorhub` (`mirrorhub.db`, `uploads\`, `apks\`, `recordings\`, `logs\`, `backups\`, `reports\`).
- Migrasi daripada `backend\mirrorhub.db` (versi sumber): disalin, disahkan `integrity_check`, tidak dialihkan; salinan `pre-migration` disimpan.
- Backup/Restore: Sistem → Cipta backup / Pulihkan (restore dijadualkan, dilaksanakan semasa mula, backup keselamatan dahulu).
- Skema: lajur baharu ditambah selepas backup `pre-schema-change`.

## Status keluaran (2026-11-08)
| Status | Keputusan | Asas |
|---|---|---|
| **SINGLE_DEVICE_READY** | **YA** — Pixel 6 (rujukan) | E2E 18/18 dalam aplikasi yang dipasang (`docs/E2E_SINGLE_DEVICE_REPORT.md`); soak 25 + 16 min tanpa reconnect/ralat, memori rata; 484 ujian lulus; smoke pemasang 18/18 dan 19/19; kemas kini di atas aplikasi berjalan lulus; tiada blocker kritikal terbuka |
| **MULTI_DEVICE_READY** | **TIDAK** (belum diuji) | 4+ telefon, input pada Redmi (disekat tetapan Xiaomi), soak 8 jam, cabut kabel fizikal, Windows bersih — `docs/HARDWARE_VALIDATION.md` |

Cakupan SINGLE_DEVICE_READY: telefon jenis Pixel/AOSP yang tidak menyekat input USB. Telefon Xiaomi/HyperOS memerlukan "USB debugging (Security settings)" dan "Install via USB" (dikesan dan dipaparkan oleh aplikasi). Pemasang belum ditandatangani (SmartScreen akan memberi amaran).

## Ringkasan pengesahan
- Backend: **484 lulus, 14 dikuarantin (docs/TEST_QUARANTINE.md)**, liputan teras 73.6 % (gate 60 %), seluruh kod ≈ 46 %.
- Pemasang: smoke 18/18 (normal) dan 19/19 (profil terpencil); kemas kini-di-atas-berjalan PASS. Windows bersih: BLOCKED (Windows Home).
- Perkakasan: lihat `docs/E2E_SINGLE_DEVICE_REPORT.md` dan `docs/HARDWARE_VALIDATION.md`.
- Checksum pemasang: `dist/SHA256SUMS.txt`.

## Perkara menunggu pemilik sebelum pengedaran awam
1. Semakan lesen redistribusi `adb` (Android SDK terms) dan konfigurasi binaan FFmpeg (`packaging/THIRD_PARTY_NOTICES.txt`).
2. Tandatangan kod (Authenticode) — pemasang belum ditandatangani; Windows SmartScreen akan memberi amaran.
3. Ujian pada Windows bersih dan matriks telefon (H1–H15).
4. Push ke `main` hanya selepas semakan (kerja ada pada `dev/desktop-v1`).
