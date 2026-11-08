# Checklist Pengesahan Perkakasan

Tujuan: bukti **telefon sebenar** untuk item `NOT TESTED` dalam `docs/QA_MATRIX.md`. Simulasi/unit test tidak dikira.
Alat: `MirrorHub.exe --hwcheck [--serial X] [--seconds N] [--profile thumb|normal|focus] [--allow-input]` (atau `python -m app.tools.hwcheck`).
Tanpa `--allow-input` alat hanya **membaca** (maklumat peranti, tangkapan skrin, senarai `/sdcard` — bilangan sahaja — dan strim video yang dikira, tidak disimpan). `--allow-input` menekan HOME dan BACK pada telefon.

Rekod hasil dalam QA_MATRIX (PASS / FAIL + tarikh + model + Android + sambungan).

## A. Sudah dibuktikan pada perkakasan (2026-11-08, mesin pembangun, telefon pemilik)
Sumber: `docs/HWCHECK_SAMPLE_2026-11-08.md`, sesi pengujian.
| Item | Peranti | Hasil |
|---|---|---|
| ADB mengesan, maklumat peranti (model/Android/bateri/storan/skrin) | Pixel 6 (Android 17, WiFi mDNS), Redmi 24094RAD4G (Android 16, USB) | PASS |
| Tangkapan skrin PNG | kedua-duanya | PASS |
| Senarai fail `/sdcard`, senarai pakej pihak ketiga (bilangan sahaja) | kedua-duanya | PASS |
| scrcpy-server 4.0 `raw_stream` dilancarkan, bingkai diterima | kedua-duanya, **serentak** | PASS — bingkai pertama 1.1–2.7 s; Pixel 10.2 fps / 803 kbit/s pada skrin bergerak; CPU backend 0.06 s/8 s |
| Nyahkod WebCodecs dalam Chrome, 2 kanvas serentak mengandungi piksel sebenar | kedua-duanya | PASS (diukur dengan statistik canvas; imej tidak disimpan) |
| Automasi baca sahaja: tunggu, tangkap skrin, uiautomator dump | kedua-duanya | PASS |
| Daftar automatik, USB+WiFi dikenali, offline dikesan semasa mula | 3 entri adb | PASS |

## B. Belum diuji — perlu anda (dengan telefon)
Tandakan dan rekod. Sebelum item bertanda ⚠ pastikan telefon selamat untuk disentuh (skrin utama, tiada mesej separuh siap).

| # | Ujian | Cara | Lulus jika |
|---|---|---|---|
| H1 ⚠ | Kawalan input: ketik, leret, tekan lama, taip, Back/Home/Recents | Device Wall → Fokus → klik/seret; atau `--hwcheck --allow-input` | Tindakan berlaku pada telefon **yang betul sahaja** (cuba 2 telefon) |
| H2 ⚠ | Tiada input silang | Pada Wall dengan 2 telefon, klik telefon A berulang kali | Telefon B tidak bergerak |
| H3 | FPS sebenar | Mainkan video / skrol pada telefon semasa `--hwcheck --seconds 30 --profile focus` | ≥ 24 fps (normal) dilaporkan; rekod CPU |
| H4 | 4 telefon serentak | Sambung ≥ 4, buka Wall (profil thumb) 10 minit | Semua bergerak; CPU/RAM PC munasabah (rekod Task Manager) |
| H5 | Cabut USB | Cabut kabel semasa strim | Tile → "terputus", toast; kabel dipasang semula → strim pulih sendiri < 15 s |
| H6 | WiFi putus | Matikan WiFi telefon 20 s, hidupkan | Status "Menyambung semula" → Online (jika port tidak berubah) |
| H7 | Reboot telefon | Reboot semasa strim | Offline → authorized → pulih; tiada ranap |
| H8 | Unauthorized | Revoke USB authorizations, sambung | Status "Perlu kebenaran" + arahan; selepas Allow → Online |
| H9 | Pasang APK ke 2 telefon | Apl & APK → pilih 2 → Pasang | Keputusan per telefon; sebab kegagalan jelas (cuba APK downgrade) |
| H10 | Muat naik/turun fail | Fail 1 GB + fail nama berspasi/Unicode | Saiz & hash sama |
| H11 | Rakaman skrin | `POST /devices/{id}/record/start?seconds=10` + `stop` | MP4 boleh dimainkan |
| H12 | Pairing WiFi sebenar | Pair + connect + discover pada Android 11+ | Berfungsi tanpa kabel |
| H13 | Soak 8 jam | Wall dengan ≥ 2 telefon semalaman | Tiada kebocoran memori (RAM stabil), tiada ranap, strim hidup |
| H14 | Pelbagai OEM | Samsung / Xiaomi / Oppo / Vivo | Strim + input OK (Xiaomi perlu Security settings) |
| H15 | Pemasang pada Windows bersih | VM/PC tanpa Python/Node | `packaging\smoke_installer.ps1` 18/18 + buka manual |

## C. Pemerhatian semasa ujian pertama
- Entri adb `TSNFNVBEMBMFQG4X` kekal `offline` (peranti USB kedua yang tidak sedia). Mirrorhub melaporkannya dengan arahan; punca pada sisi telefon/kabel.
- Pixel 6 melalui mDNS: `wlan0` IP tidak dapat dibaca (medan `wifi_ip` kosong) — kosmetik.
