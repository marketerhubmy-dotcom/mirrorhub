# DEVELOPMENT STATUS — Mirrorhub V1.1 (checkpoint)

Dikemas kini: 2026-11-09 · Branch: `dev/performance-v1.1` (dari `dev/desktop-v1`) · `main` tidak disentuh.

## Siap dan lulus (dengan bukti)
- Halaman **Prestasi** (kad, 8 graf + sejarah 5m/15m/1j/sesi, jadual per peranti dengan N/A+sebab, kesihatan idle≠rosak, amaran dengan hysteresis+cooldown, log peristiwa, laporan/eksport JSON/CSV tanpa rahsia) — `docs/PERFORMANCE_DASHBOARD.md`.
- Kestabilan multi-device: pengasingan strim/input (HW 2 × Pixel 6), pelepasan soket, pembaikan kebocoran di punca (K29), reconnect per gangguan (K31).
- Pembetulan rakaman skrin (K38, ditemui semasa regresi HW).
- Ujian: backend 553 lulus / 14 dikuarantin, liputan teras ≈ 79 % (gate 60 %); frontend tsc + build + vitest 13.
- Pemasang `dist/Mirrorhub-Setup-1.1.0.exe` (40.7 MB), SHA-256 `88E86A8C05B19BAFE95AB44CAA41C2BC1BFE1A7EA86FDD3687E20D76D79FCABD`; smoke 19/19 (normal) + 20/20 (terpencil); kemas kini 1.0.0 → 1.1.0 mengekalkan data.
- HW (Pixel 6 B, aplikasi dipasang): regresi satu telefon 3/3 ALL PASS; soak 30 min (RSS +4.9 MB, 0 reconnect/ralat).

## Gagal / diperbaiki semasa sesi
Lihat `docs/KNOWN_ISSUES.md` K28–K32, K38. Tiada kegagalan terbuka yang diketahui dalam skop V1.1.

## BLOCKED / NOT TESTED
- BLOCKED: dua telefon bergerak serentak (Pixel A dikunci), 4+/9 telefon (hanya 2), Redmi (tetapan keselamatan Xiaomi), cabut USB/WiFi off/reboot, Windows bersih (Windows Home).
- NOT TESTED: soak 8 jam (terpanjang 30 min), latency tap→bingkai, amaran RAM/CPU/memori sebenar pada HW.

## Status keluaran
V1.1_READY = YA · SINGLE_DEVICE_READY = YA · **MULTI_DEVICE_READY = TIDAK (belum diuji)**.

## Tindakan pemilik
Buka kunci kedua-dua telefon / sediakan 4+ telefon; soak 8 jam; ujian cabut kabel/reboot; tetapan Xiaomi untuk Redmi; Windows bersih; semakan lesen adb/FFmpeg + tandatangan kod; semak sebelum merge ke `main`.

## Tugas seterusnya
Ujian MULTI_DEVICE sebenar (4 → 9 telefon), soak 8 jam, latency tap→bingkai, kekalkan sejarah prestasi (K35). Fasa 06–09 belum dimulakan.
