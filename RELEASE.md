# RELEASE

# V1.1.0 — Multi-Device Stability + Performance Dashboard (2026-11-09)

## Status
| Status | Keputusan | Asas |
|---|---|---|
| **V1.1_READY** | **YA** | Semua kriteria penerimaan dipenuhi dengan bukti (lihat bawah); fungsi Single Device Ready kekal berfungsi pada Pixel 6 (kemas kini di atas v1.0.0, E2E klik-tap-swipe-Home-Back melalui Wall diulang, APK/fail/reconnect tidak berubah kodnya selain pembaikan) |
| **SINGLE_DEVICE_READY** | **YA** (kekal) | `docs/E2E_SINGLE_DEVICE_REPORT.md` (v1.0) + soak 30 min dipasang v1.1.0 |
| **MULTI_DEVICE_READY** | **TIDAK (belum diuji)** | hanya 2 telefon; 4+ telefon, soak 8 jam, cabut kabel fizikal, Redmi, Windows bersih belum — `docs/HARDWARE_VALIDATION.md` (V1.1: B1–B5) |

## Artifak
| Fail | Keterangan |
|---|---|
| `dist/Mirrorhub-Setup-1.1.0.exe` | Pemasang Windows x64, per-pengguna, tanpa admin (40.7 MB). SHA-256 `88E86A8C05B19BAFE95AB44CAA41C2BC1BFE1A7EA86FDD3687E20D76D79FCABD` (juga dalam `dist/SHA256SUMS.txt`) |
`dist/` dan `build/` tidak dikomit (dijana). Binari pihak ketiga (`tools/`) dibundel oleh pemasang (ADR-006; semakan lesen adb/FFmpeg masih menunggu pemilik).

## Apa baharu
- **Prestasi** (sidebar): kad kesihatan/peranti/strim/FPS/CPU+RAM PC dan proses Mirrorhub (dipisahkan)/reconnect; 8 graf langsung dengan sejarah 5 min/15 min/1 jam/sesi (had memori berhad); jadual per peranti (FPS, resolusi daripada SPS, bitrate, masa mula, reconnect, uptime, bateri, bingkai dihantar/digugurkan, statistik penyahkod pelayar, ralat terakhir) dengan **N/A + sebab**; kesihatan (Sihat/Terjejas/Menyambung semula/Terputus/Perlu kebenaran) yang membezakan **idle daripada bermasalah**; amaran (RAM, CPU, gelung reconnect, strim tersangkut, pertumbuhan memori, terlalu banyak strim) dengan hysteresis + cooldown dan toast; ambang boleh dikonfigurasi; log peristiwa; **salin laporan / eksport JSON / CSV** tanpa rahsia. Dokumen: `docs/PERFORMANCE_DASHBOARD.md`.
- **Kestabilan multi-device**: pengasingan kegagalan strim, pelepasan sesi/soket, pembaikan kebocoran di punca (lihat `KNOWN_ISSUES` K29–K32), pelaporan reconnect per gangguan.
- **Pembetulan rakaman skrin** (K38): rakam ke `/data/local/tmp`, tunggu fail siap, sahkan MP4 (`moov`); ralat jelas jika tidak lengkap. Ditemui semasa regresi perkakasan.
- Backend: `/api/v1/perf/*`; adb dijalankan melalui thread (tiada subproses asyncio berkitar); `gc` global hanya jaring keselamatan 5 min.
- Frontend: vitest (13 ujian) dalam binaan.

## Kemas kini daripada 1.0.0
Jalankan `Mirrorhub-Setup-1.1.0.exe` di atas pemasangan lama (AppId sama; aplikasi yang berjalan ditutup sendiri). Data `%APPDATA%\Mirrorhub` (pangkalan data, tetapan, peranti, backup) kekal — disahkan pada pemasangan sebenar (versi 1.0.0 → 1.1.0, peranti/nama/tag/keutamaan utuh). Tetapan baharu (ambang prestasi) mengambil nilai lalai.

## Pengesahan (ringkas; butiran dalam QA_MATRIX / HARDWARE_VALIDATION)
- Backend **553 lulus, 14 dikuarantin**; liputan teras 79.1 %, seluruh kod 52.2 %. Frontend `tsc`, `vite build`, vitest 13 lulus.
- Pemasang 1.1.0: smoke 19/19 (normal), 20/20 (profil terpencil); kemas kini dari 1.0.0 lulus. **Windows bersih: BLOCKED (Windows Home).**
- Perkakasan (2 × Pixel 6): pengasingan input, dashboard sebenar, amaran sebenar, reconnect, soak 30 min dipasang (RSS +4.9 MB, 0 reconnect, 0 ralat). **Bukan soak 8 jam.**

## Perkara menunggu pemilik
1. Semakan lesen redistribusi `adb` / FFmpeg; tandatangan kod (SmartScreen).
2. Ujian MULTI_DEVICE: 4+ telefon (buka kunci semua), cabut kabel/WiFi off/reboot, Redmi (tetapan keselamatan Xiaomi), soak 8 jam, Windows bersih.
3. Semak dan lulus sebelum gabung ke `main` (kerja pada `dev/performance-v1.1`).

---

# V1.0.0 (sebelumnya)


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
