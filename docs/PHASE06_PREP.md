# Fasa 06 — Local Virtual Android: persiapan (BELUM dibina)

Status: **persiapan sahaja**. Tiada emulator dijalankan; tiada kod Fasa 06 dalam produk kecuali pengesanan SDK dalam Diagnostik.

## Keadaan mesin (audit 2026-11-08)
| Item | Nilai | Implikasi |
|---|---|---|
| RAM | 23.2 GB | 2 emulator (2–3 GB RAM tetamu masing-masing) munasabah; 4+ tidak bersama Device Wall |
| Cakera bebas | ~18 GB | Imej sistem API 34 (+Google APIs) ≈ 1.5–2.5 GB, AVD ≈ 3–7 GB data setiap satu — **ruang adalah kekangan utama** |
| Virtualisasi firmware | Enabled | Perlu Windows Hypervisor Platform (WHPX) atau AEHD; semak `systeminfo`/Windows Features |
| JDK / Android SDK / emulator | **tiada** | Blocker — pemasangan memerlukan persetujuan pemilik |

## Reka bentuk (apabila SDK ada)
1. Pengesanan: `ANDROID_HOME`/`ANDROID_SDK_ROOT`, `%LOCALAPPDATA%\Android\Sdk`, `emulator.exe`, `cmdline-tools\latest\bin\{sdkmanager,avdmanager}.bat`.
2. Modul `app/virtual/` (belum wujud): `list_avds`, `create_avd(name, api, device)`, `start(name, port)` dengan `-no-window -no-audio -no-boot-anim -gpu swiftshader_indirect|host -port N -read-only?`, `stop` (`adb -s emulator-N emu kill`), pemantauan boot (`sys.boot_completed`).
3. **Integrasi sedia ada:** emulator muncul dalam `adb devices` sebagai `emulator-5554`; `adb_client.classify_transport` sudah mengenalinya (`emulator`) dan `DeviceMonitor` mendaftarkannya → strim scrcpy, kawalan, APK, fail dan automasi berfungsi tanpa perubahan. Kerja baharu hanyalah kitaran hayat (cipta/mula/henti/padam) dan UI "Telefon maya".
4. Sempadan keselamatan: nama AVD `^[A-Za-z0-9_.-]{1,40}$`; arahan melalui argv; port emulator dalam julat 5554–5584 genap; `emulator` hanya bind loopback (lalai).
5. Had: aplikasi dengan Play Integrity/anti-emulator tidak akan berfungsi; Mirrorhub **tidak** akan menyembunyikan status emulator (peraturan tanpa stealth).

## Kriteria penerimaan Fasa 06 (rancangan induk)
2 emulator serentak, dikawal dari Device Wall yang sama, snapshot/cipta/padam melalui UI, ujian benar (bukan simulasi) pada mesin ini.

## Langkah pemilik untuk membuka blocker
1. Luluskan pemasangan JDK 17 (Temurin) dan Android command-line tools (+ `platform-tools`, `emulator`, 1 imej sistem `google_apis;x86_64` API 34) ≈ 6–9 GB.
2. Pastikan WHPX diaktifkan (Windows Features → *Windows Hypervisor Platform*), mulakan semula.
