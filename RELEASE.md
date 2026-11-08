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

## Pengesahan sebelum keluaran (keadaan semasa)
Lihat `docs/QA_MATRIX.md`. Ringkasan:
- Ujian backend: **457 lulus, 14 dikuarantin (docs/TEST_QUARANTINE.md)**, gate liputan 60 % (skop teras V1) = **75 %**; keseluruhan kod = 46 %.
- Pemasang: 18/18 smoke pada mesin pembangun. **Windows bersih: NOT TESTED.**
- Perkakasan: strim, nyahkod, maklumat, tangkapan, fail, automasi baca-sahaja = PASS pada 2 telefon (Pixel 6, Redmi). Kawalan input, kehilangan sambungan, 4+ telefon, soak = **NOT TESTED** (`docs/HARDWARE_VALIDATION.md`).

## Perkara menunggu pemilik sebelum pengedaran awam
1. Semakan lesen redistribusi `adb` (Android SDK terms) dan konfigurasi binaan FFmpeg (`packaging/THIRD_PARTY_NOTICES.txt`).
2. Tandatangan kod (Authenticode) — pemasang belum ditandatangani; Windows SmartScreen akan memberi amaran.
3. Ujian pada Windows bersih dan matriks telefon (H1–H15).
4. Push ke `main` hanya selepas semakan (kerja ada pada `dev/desktop-v1`).
