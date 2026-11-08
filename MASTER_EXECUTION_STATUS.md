# MASTER EXECUTION STATUS

Dikemas kini: 2026-11-08 · Branch: `dev/desktop-v1` (dipush ke `origin`) · `main` = baseline sahaja (tiada kod baharu tanpa semakan).

| Fasa | Status | Bukti / catatan |
|---|---|---|
| 00 Audit | **SIAP** | `docs/AUDIT.md`, ADR 001–009 |
| 01 Desktop foundation | **SIAP (kod+ujian); installer diuji pada mesin pembangun** | AppData + migrasi/backup/restore; loopback guard; desktop selftest; PyInstaller + Inno Setup; smoke 18/18 |
| 02 Multi-phone mirroring | **SIAP (HW separa)** | 2 telefon sebenar serentak (strim+nyahkod). Input HW, 4+ telefon, soak = NOT TESTED |
| 03 Device management | **SIAP (HW separa)** | Pairing Center, lifecycle (hot-plug/unauthorized/reconnect), Device Manager, diagnostik |
| 04 APK & fail | **SIAP (sim); HW baca-sahaja PASS** | Pasang/muat naik/padam diuji dengan adb palsu; belum pada telefon (H9–H11) |
| 05 Automasi + kebolehpercayaan | **SIAP (sim); HW baca-sahaja PASS** | enjin 45 ujian; langkah yang menggerakkan telefon belum diuji (H1) |
| 05 Pemasang | **SIAP (mesin pembangun)** | `dist/Mirrorhub-Setup-1.0.0.exe` 40.6 MB; Windows bersih NOT TESTED; belum ditandatangani |
| 06 Local Virtual Android | **Persiapan sahaja** | tiada JDK/Android SDK; lihat `docs/PHASE06_PREP.md` |
| 07–09 Remote/Cloud/SaaS | Tidak dimulakan | perlukan kelulusan pemilik (cloud/bayaran) |

Ujian: backend 457 lulus / 14 dikuarantin; liputan teras 75.3 % (gate 60 %), seluruh kod 46 %; frontend `tsc` + `build` lulus.

## Kemas kini pengesahan perkakasan (2026-11-08)
Lihat `docs/HARDWARE_VALIDATION.md`: Pixel 6 lulus kawalan input, reconnect, APK, fail; Redmi disekat oleh tetapan keselamatan Xiaomi (BLOCKED, bukan FAIL). Desktop V1 **belum** melepasi acceptance criteria penuh — Fasa 06–09 dan merge ke `main` ditangguhkan.

## Keluaran satu telefon (2026-11-08)
**SINGLE_DEVICE_READY = YA (Pixel 6)**; **MULTI_DEVICE_READY = TIDAK (belum diuji)**. Lihat `RELEASE.md`, `docs/E2E_SINGLE_DEVICE_REPORT.md`, `docs/SETUP_GUIDE.md`. Fasa 06–09 belum dimulakan; tiada merge ke `main`.

## V1.1 Performance (2026-11-09)
Branch `dev/performance-v1.1`: dashboard Prestasi + kestabilan multi-device + pemasang 1.1.0. **V1.1_READY = YA; MULTI_DEVICE_READY = TIDAK (belum diuji)**. Lihat `DEVELOPMENT_STATUS.md`, `RELEASE.md`.

## Blocker / tindakan pemilik
1. Ujian input pada telefon sebenar (H1/H2) — saya tidak menyentuh skrin telefon anda tanpa kebenaran; jalankan `MirrorHub.exe --hwcheck --allow-input` atau kawal melalui Wall.
2. Windows bersih untuk smoke installer (H15); tandatangan kod; semakan lesen adb/FFmpeg.
3. Kelulusan semakan sebelum `dev/desktop-v1` digabung ke `main`.
4. Fasa 06: pasang JDK 17 + Android SDK (≈ 8–10 GB) — memerlukan persetujuan anda.
