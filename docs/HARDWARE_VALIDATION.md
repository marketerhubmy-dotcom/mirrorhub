# Checklist Pengesahan Perkakasan

Tujuan: bukti **telefon sebenar** untuk item dalam `docs/QA_MATRIX.md`. Simulasi/unit test tidak dikira sebagai PASS perkakasan.
Alat: `MirrorHub.exe --hwcheck [--serial X] [--seconds N] [--profile thumb|normal|focus] [--allow-input]`, `python -m app.tools.soak --minutes N [--churn S]` (backend mesti berjalan).

Peranti ujian (mesin pembangun, telefon pemilik): **Pixel 6** (Android 17, ADB WiFi/mDNS) dan **Redmi 24094RAD4G / HyperOS** (Android 16, USB). Satu entri USB ketiga (`TSNF…`) sentiasa `offline`/`unauthorized` dan tidak disentuh.
Kebenaran pemilik 2026-11-08: tap, swipe, taip teks ujian, Home, Back, pasang/periksa APK, fail ujian. **Tidak** dibenarkan: mesej sebenar, pembelian, memadam data, mengubah tetapan keselamatan, reboot. Semua dipatuhi (tiada tetapan diubah, tiada data pengguna dipadam; fail ujian dalam folder sendiri dipadam).

Legenda: **PASS** (bukti perkakasan) · **FAIL** · **BLOCKED** (punca luar kawalan, dinyatakan) · **NOT TESTED**.

## PASS — bukti perkakasan sebenar (2026-11-08)
| # | Ujian | Peranti | Bukti |
|---|---|---|---|
| P1 | ADB mengesan; maklumat model/Android/bateri/storan/skrin | Pixel, Redmi | `docs/HWCHECK_SAMPLE_2026-11-08.md` |
| P2 | Tangkapan skrin PNG; senarai fail; senarai pakej | Pixel, Redmi | 173–212 KB PNG sah; 8/20 folder; 40/51 pakej |
| P3 | Strim scrcpy 4.0 `raw_stream` + nyahkod Chrome, **2 telefon serentak** | Pixel, Redmi | bingkai pertama 1.1–2.7 s; Pixel 10.2 fps @ 803 kbit/s (skrin bergerak); 2 kanvas berisi piksel |
| P4 | **H1 Kawalan input melalui Device Wall — Pixel:** Home (apl latar depan TikTok → Launcher), swipe dari atas (skrin berubah, diff 70.7), Back (kembali, diff 0.0), tap pada bar alamat Chrome (dipetakan tepat), taip "mirrorhub input test" (teks tiba utuh, `url_bar` diverifikasi) | Pixel | log audit `mirrorhub.control.audit` menunjukkan **hanya** `device=Pixel`; `dumpsys activity` + perbezaan tangkapan skrin |
| P5 | **Reconnect:** dua laluan WiFi untuk satu telefon → **satu** baris peranti | Pixel | hw serial sama |
| P6 | **Adb server dimatikan** (kehilangan semua transport) → pulih sendiri | Pixel, Redmi | Pixel offline → online ≈ 7 s (percubaan 1) |
| P7 | `adb reconnect` pada laluan `ip:port` → pulih sendiri | Pixel | reconnecting → online ≈ 8 s |
| P8 | Putus manual (Pairing API) **tidak** mencetus sambung semula | Pixel | tiada ribut reconnect; kekal online melalui laluan mDNS |
| P9 | Sambung semula manual API untuk peranti mDNS (selepas pembaikan) | Pixel | `connected to 192.168.0.238:39927` |
| P10 | **APK:** muat naik ke pustaka + `install-many` serentak; Pixel: pemasangan semula `-r` (data kekal, apl masih ada); keputusan **per telefon** | Pixel | "Berjaya dipasang." |
| P11 | APK: sebab kegagalan jelas pada Redmi (`INSTALL_FAILED_USER_RESTRICTED` → arahan "Install via USB") | Redmi | mesej Bahasa Malaysia tepat |
| P12 | Buka / henti paksa Chrome; nama pakej jahat ditolak (400) | Pixel | |
| P13 | **Fail:** 200 MB rawak + nama `fail ujian é ü 日本 (1).txt` — muat naik, muat turun, **SHA-256 sama**, senarai, namakan semula, padam folder ujian sendiri; padam `/sdcard` ditolak (400) | Pixel 5/6 MB/s (WiFi), Redmi 23/30 MB/s (USB) | skrip `xfer.py` |
| P14 | Rakaman skrin 10 s → MP4 sah (`ftyp`, `moov`) | Pixel | 159 KB |
| P15 | Automasi baca sahaja: tunggu, tangkap skrin, uiautomator dump | Pixel, Redmi | enjin 3/3 langkah |
| P16 | Pengesanan input disekat: Redmi `input_state=blocked`, Pixel `ok`; WS kawalan melaporkan `input_blocked` | Redmi, Pixel | lihat BLOCKED B1 |

## BLOCKED — dengan sebab
| # | Ujian | Sebab (bukti) | Apa yang diperlukan |
|---|---|---|---|
| B1 | **Input pada Redmi** (tap/swipe/taip/Home/Back) | `SecurityException: Injecting input events requires … INJECT_EVENTS` — HyperOS menyekat input USB kerana *USB debugging (Security settings)* OFF. Skrin juga mati/terkunci semasa ujian. Mengubah tetapan keselamatan **tidak dibenarkan**. Mirrorhub kini mengesan dan memaparkan arahan (amaran pada kad peranti + mesej dalam tile) | Pemilik hidupkan *USB debugging (Security settings)* (perlu akaun Mi/SIM) dan buka kunci skrin, kemudian ulang H1/H2 pada Redmi |
| B2 | **Kawalan individu 2 telefon / tiada input silang** (H2) | Bergantung pada B1. Separa: perintah Pixel hanya dihantar kepada `device=Pixel` (log audit) dan Redmi tidak menerima apa-apa | sama seperti B1 |
| B3 | Pemasangan APK **baharu** pada Redmi | `USER_RESTRICTED` (tetapan *Install via USB*) — tetapan keselamatan | pemilik hidupkan *Install via USB* |
| B4 | **4+ telefon** (H4) | hanya 2 telefon tersedia | sambung ≥ 4 telefon |
| B5 | **Cabut kabel USB sebenar** (H5), **WiFi telefon dimatikan** (H6) | memerlukan tindakan fizikal / mematikan WiFi telefon (boleh memutuskan kawalan jauh) — tidak dilakukan | pemilik cabut kabel / matikan WiFi 20 s semasa strim |
| B6 | **Soak 8 jam (H13)** pada telefon | telefon terputus daripada PC pada akhir sesi (adb kosong); soak telefon sebenar hanya sempat 2 minit (RSS 135→158 MB masih tempoh pemanasan; **14–29 reconnect/30 s datang daripada Redmi yang skrinnya mati** — belum didiagnosis, alat soak kini mencetak sampel ralat) | sambung telefon, hidupkan skrin Redmi, `python -m app.tools.soak --minutes 480` |
| B7 | **Reboot telefon (H7)** | tidak dibenarkan oleh kebenaran pemilik | kebenaran eksplisit |
| B8 | **Windows bersih (H15)** | mesin ialah Windows 11 **Home** (tiada Hyper-V / Windows Sandbox); mencipta akaun pengguna baharu dilarang | PC/VM Windows bersih |

## NOT TESTED
| # | Ujian | Catatan |
|---|---|---|
| N1 | H3 latency hujung-ke-hujung (tap → bingkai) dan FPS ≥ 24 pada profil `focus` | telefon terputus sebelum diukur |
| N2 | H8 *revoke authorizations* → unauthorized → allow | entri `unauthorized` sebenar (`TSNF…`) dipaparkan dengan arahan, tetapi kitaran Allow tidak diuji |
| N3 | H12 pairing WiFi baharu (kod 6 digit) | telefon sudah dipasangkan; `pair` hanya diuji dengan adb palsu |
| N4 | H14 pelbagai OEM (Samsung/Oppo/Vivo) | hanya Pixel dan Xiaomi |
| N5 | Muat naik fail 1 GB | 200 MB diuji |
| N6 | Pasang `.apks/.xapk`, muat turun folder | tidak disokong (K20) |

## Bukti sokongan bukan-perkakasan (bukan PASS perkakasan)
- **Soak simulasi** (`tests/sim`, strim H.264 sintetik, 2 "telefon", viewer churn): menemui **kebocoran sebenar** — `permessage-deflate` menyimpan konteks zlib ≈ 110 KB setiap soket (≈ 2 MB/min pada churn 20 s). Dibaiki (`ws_per_message_deflate=False` dalam `desktop.py` dan `run.py`); ulang: RSS +0.0 hingga +2 MB / 2–3 min, **thread/handle stabil**, sisa pertumbuhan ialah kitaran yang dibersihkan `gc.collect()` (2.2 MB → 64 KB). Ini bukti kod, bukan perkakasan; soak telefon sebenar masih B6.

## Pemerhatian
- Redmi: strim ke telefon yang skrinnya mati tamat masa; kini UI memaparkan "Skrin telefon mati/terkunci - hidupkan skrin telefon." (bukan log mentah scrcpy).
- Pixel melalui mDNS: `adb reconnect` menghilangkan transport mDNS dan adb **tidak** menyambungnya semula; Mirrorhub kini menyelesaikan alamat semasa melalui `adb mdns services` dan menyambung (P9). Ujian auto-pulih bagi laluan bernama-mDNS khusus hanya diuji unit + manual; laluan `ip:port` diuji sebenar (P7).
- Telefon Pixel dibiarkan di Launcher (sebelum ujian di TikTok); tiada data diubah. Pixel mungkin masih ada Chrome terbuka di `about:blank`.
