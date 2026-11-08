# Penyelesaian Masalah

Mulakan dengan **Sistem → Diagnostik** atau `MirrorHub.exe --diag` (tambah `--json`). Log: `%APPDATA%\Mirrorhub\logs\mirrorhub.log`.

| Gejala | Punca lazim | Penyelesaian |
|---|---|---|
| Telefon tidak muncul (USB) | Kabel cas sahaja; USB debugging OFF; pemacu | Guna kabel data; hidupkan USB debugging; pasang pemacu USB pengeluar. `adb devices` mesti menyenaraikan telefon |
| Status **Perlu kebenaran** | Dialog "Allow USB debugging" belum diterima | Buka kunci telefon, tekan *Allow* (Always allow). Jika dialog tidak muncul: Developer options → *Revoke USB debugging authorizations* → cabut/pasang kabel |
| Status **offline** (adb) | Sesi adb rosak | Cabut/pasang kabel; matikan/hidupkan USB debugging; Sistem → Diagnostik |
| WiFi: "Sambungan ditolak" | Port Wireless debugging berubah | Baca port **terkini** pada skrin Wireless debugging; sambung semula |
| WiFi: pairing gagal | Kod tamat tempoh / salah port | Tekan semula *Pair device with pairing code*; guna alamat pairing (bukan alamat sambungan) |
| WiFi tidak ditemui oleh *Imbas rangkaian* | mDNS disekat router/firewall/VPN | Taip IP:port secara manual; matikan VPN; PC & telefon dalam rangkaian yang sama |
| Wall: "Menunggu video…" lama / ralat | Pelayan skrin gagal bermula | Skrin telefon mesti tidak dilindungi; Xiaomi: hidupkan *USB debugging (Security settings)*; tutup aplikasi lain yang menangkap skrin (Vysor, scrcpy lama) |
| Wall: skrin hitam pada aplikasi tertentu | Aplikasi menetapkan FLAG_SECURE (perbankan, dsb.) | Dengan reka bentuk Android; tidak boleh dipintas |
| Wall: 0 fps | Skrin statik | Normal — encoder hanya menghantar apabila ada perubahan |
| Klik tidak berfungsi pada Xiaomi/Redmi/Poco | Kawalan input USB disekat | Developer options → hidupkan **USB debugging (Security settings)** (perlu SIM/akaun Mi) |
| Pasang APK: `INSTALL_FAILED_USER_RESTRICTED` | Sekatan pemasangan USB | Hidupkan *Install via USB*; terima dialog pada telefon |
| "adb.exe tidak dijumpai" | Pemasangan rosak / antivirus | Pasang semula; semak antivirus (kuarantin `adb.exe`) |
| Aplikasi dibuka dalam pelayar, bukan tetingkap | WebView2 tiada | Pasang *Microsoft Edge WebView2 Runtime*; tiada kehilangan fungsi |
| Aplikasi tidak bermula, mesej port | Port 8000 digunakan program lain | Mirrorhub memilih port bebas secara automatik; jika masih gagal tutup program yang menggunakan port itu |
| Mahu pulihkan data | — | Sistem → Backup → Pulihkan; atau salin backup dari `%APPDATA%\Mirrorhub\backups` |
| Menyahpasang tidak memadam data | Dengan reka bentuk | Padam `%APPDATA%\Mirrorhub` secara manual jika mahu |

## Kumpul maklumat untuk laporan
1. `MirrorHub.exe --diag --json > diag.json`
2. Dengan telefon disambung: `MirrorHub.exe --hwcheck --seconds 15` (baca sahaja) → laporan di `%APPDATA%\Mirrorhub\reports\`.
3. Lampirkan 200 baris terakhir `logs\mirrorhub.log` (semak dahulu — log tidak mengandungi kata laluan tetapi mengandungi alamat IP dan nama peranti).

## Pengesahan perkakasan
Lihat `docs/HARDWARE_VALIDATION.md`.
