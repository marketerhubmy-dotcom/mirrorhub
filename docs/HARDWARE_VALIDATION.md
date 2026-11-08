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


---

# V1.1 — Multi-Device Stability + Performance Dashboard (2026-11-09)

Peranti: **dua Pixel 6 berbeza** (Android 17, ADB WiFi/mDNS; nombor siri perkakasan berbeza → dua baris peranti berasingan walaupun model sama). Redmi dan peranti USB lain tidak hadir. Aplikasi diuji dalam bentuk **dipasang v1.1.0** (kemas kini di atas v1.0.0) selain pelayan pembangun untuk diagnosis.
Kebenaran: tap/swipe/Back/Home, tiada tindakan merosakkan. Semasa sesi **satu Pixel dikunci (keyguard)**; saya tidak membuka kunci dan menandakan ujian yang memerlukannya sebagai BLOCKED.

## PASS (bukti perkakasan)
| # | Ujian | Bukti |
|---|---|---|
| V1 | **Pengasingan input dua telefon melalui Device Wall**: swipe pada tile kiri → hanya telefon A berubah (diff 72.9), B 0.08; Back kiri → A pulih; swipe tile kanan → hanya B (114.1), A 0.07; Back+Home kanan → kedua-duanya pulih; log audit memetakan setiap arahan kepada peranti yang betul | skrip `iso.py` (perbezaan tangkapan skrin per telefon + audit) |
| V2 | **Dua peranti serupa, dua identiti** (model sama, siri perkakasan berbeza) | 2 baris, `device_id` berbeza, strim serentak |
| V3 | Dashboard memaparkan metrik sebenar: CPU/RAM PC (RAM 16.1/23.2 GB sepadan mesin), CPU proses Mirrorhub dipisahkan (0.1–0.3 %), RSS, thread, handle | `/perf/snapshot`, tangkapan skrin UI |
| V4 | **Resolusi daripada SPS** = 432×960 sepadan kanvas pelayar (penghurai SPS disahkan pada perkakasan) | `/perf/devices` vs kanvas |
| V5 | **Aktif vs idle** dibezakan: telefon bergerak 19–24 fps / 2.0–2.9 Mbps = *active, sihat*; telefon statik 0 fps = *idle, sihat* (bukan rosak) | `motion_probe.py`, `load1.py` |
| V6 | Dua penemuan kesihatan palsu dibetulkan melalui perkakasan: (a) letusan keyframe awal dikira aktif → *warmup* 10 s; (b) letusan notifikasi singkat → perlu aktiviti berterusan ≥ 3 sampel dan FPS terkini | ujian regresi + ulang pada telefon |
| V7 | **Reconnect dilihat melalui dashboard**: `adb reconnect` → `reconnecting` → `healthy`; log peristiwa merekod urutan; **satu gangguan = satu reconnect** (sebelum ini 5 percubaan = 5, mencetus amaran "gelung" palsu) | `recon_dash.py` |
| V8 | **Amaran sebenar**: ambang `perf_max_streams` diturunkan kepada 1 dengan 2 strim aktif → sepanduk + status "Perlu perhatian" dalam ≈ 6 s; ambang dipulihkan → *cleared*; sejarah `triggered`/`cleared` | UI + `/perf/alerts` |
| V9 | **Eksport diagnostik**: JSON (35 KB) dijana melalui butang; tiada kunci/rahsia; **ditemui** nama peranti berbentuk IP membocorkan alamat → dibetulkan (dimasking) + ujian | JS menangkap blob eksport |
| V10 | Soket dilepaskan: meninggalkan Device Wall menurunkan soket video 4 → 2 serta-merta (baki ialah penonton luar); sesi strim dituai selepas 5 s | `/perf/overview` WS gauge |
| V11 | **Soak 12 min, 2 telefon, tanpa gelung GC**: 0 reconnect, 0 ralat; thread 16 stabil; handle stabil | `soak_v11_nogc.log` |
| V12 | **Soak 30 min, aplikasi dipasang v1.1.0, 2 telefon**: 0 reconnect, 0 ralat; RSS **205.4 → 210.3 MB (+4.9)**; thread 16→16; handle 570→557 (sebelum pembaikan punca: ≈ +5.5 MB/**min**) | `soak_v11_installed.log` |
| V13 | Beban: idle PC CPU 10.3 % / Mirrorhub 0.13 % / RSS 212 MB → satu telefon bergerak 24 fps (2.9 Mbps): PC 12.2 % (maks 16.4), Mirrorhub 0.3 % (maks 0.7), RSS 213 MB | `load1.py` (CPU PC termasuk penyahkodan pelayar Chrome) |
| V14 | Kemas kini pemasang v1.0.0 → v1.1.0 di atas pemasangan sebenar: versi 1.1.0, data/tetapan/peranti kekal, pintasan utuh, tetingkap terbuka | PowerShell |
| V15 | **Regresi satu telefon pada aplikasi dipasang v1.1.0** (Pixel 6 B): tangkapan skrin PNG, muat naik/muat turun fail 8 MB (SHA-256 sepadan, nama berspasi/kurungan), pemasangan + nyahpasangan APK ujian sendiri, rakaman MP4 sah (`ftyp`+`moov`), automasi 3 langkah — **ALL PASS 3/3 larian berturut-turut** | `regress.py` |
| V16 | **Penemuan: rakaman tidak lengkap** — selepas pasang/nyahpasang APK, `screenrecord` tersekat ≈ 9 s dalam `fuse_simple_request` (logcat: pengekod bermula 9 s selepas pelancaran) → rakaman dihentikan awal = MP4 3232 B tanpa `moov` (6/6 gagal dalam keadaan itu). Dibetulkan (K38): rakam ke `/data/local/tmp`, 5/5 lulus dalam keadaan yang sama; pengesahan kelengkapan + ralat jelas | `recbis.py`, logcat |

## BLOCKED
| # | Ujian | Sebab |
|---|---|---|
| B1 | **Dua telefon bergerak serentak** (FPS/CPU di bawah beban dua strim aktif) | Pixel A dikunci (keyguard) — tidak dibuka; hanya satu telefon boleh digerakkan |
| B2 | **4 telefon**, kemudian 9 | hanya 2 telefon fizikal |
| B3 | Redmi: input/APK | tetapan keselamatan Xiaomi (sama seperti V1.0) |
| B4 | Cabut kabel USB, WiFi telefon off, reboot | tindakan fizikal / tiada kebenaran |
| B5 | Windows bersih | Windows 11 Home (tiada VM/Sandbox) |

## NOT TESTED
Soak 8 jam (terpanjang pada perkakasan: 30 min); latency tap→bingkai; amaran RAM/CPU tinggi dan pertumbuhan memori sebenar (hanya unit; hanya `too_many_streams` dicetus pada perkakasan); statistik penyahkod pelayar dibandingkan dengan kaunter dalaman pelayar. **4-device PASS tidak dituntut.**

## Bukti sokongan simulasi (bukan perkakasan)
- Soak 8 min, **9 telefon simulasi**, penonton ditutup-buka setiap 15 s (31 kitaran/peranti, ≈ 60 000 bingkai): 0 reconnect/ralat, thread/handle stabil, RSS 96→113 MB (selebihnya sampah kitaran yang dibersihkan GC).
- Analisis punca (`gc.DEBUG_SAVEALL`): (1) struktur ctypes dicipta setiap sampel; (2) subproses asyncio untuk setiap poll adb (PipeHandle/Transport); (3) tugas WebSocket dibatalkan tidak di-`await` (Task/Coroutine/AsyncExitStack); (4) fail reaper tidak dibersihkan. Semua dibaiki di punca; GC global kini hanya jaring keselamatan 5 min (bukan pengganti pembaikan).
