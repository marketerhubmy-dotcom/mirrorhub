# Panduan Pemasangan dan Mula Pantas (satu telefon)

Untuk pengguna harian. Tiada Python, Node, VS Code atau arahan terminal diperlukan.

## A. Pasang
1. Jalankan `Mirrorhub-Setup-1.0.0.exe`. Sahkan checksum (pilihan): `Get-FileHash .\Mirrorhub-Setup-1.0.0.exe -Algorithm SHA256` mesti sama dengan `SHA256SUMS.txt`.
2. Windows SmartScreen mungkin memberi amaran kerana pemasang **belum ditandatangani**: *More info → Run anyway*.
3. Tiada akaun admin diperlukan. Lalai: `%LOCALAPPDATA%\Programs\Mirrorhub`. Pilih "Create a Desktop shortcut" jika mahu.
4. Buka **Mirrorhub** daripada Start Menu atau Desktop. Backend bermula sendiri; menutup tetingkap menghentikannya.

Data anda (pangkalan data, tetapan, backup, log, APK, rakaman): `%APPDATA%\Mirrorhub`. Menyahpasang tidak memadamnya.

## B. Sediakan telefon (sekali)
1. Settings → About phone → ketuk **Build number** 7 kali.
2. Settings → System → Developer options → hidupkan **USB debugging** (dan **Wireless debugging** untuk WiFi).
3. Xiaomi/Redmi/Poco sahaja: hidupkan juga **USB debugging (Security settings)** dan **Install via USB** — tanpanya skrin boleh dilihat tetapi sentuhan/taip dan pemasangan APK disekat (Mirrorhub akan memaparkan amaran).

## C. Sambung
**USB (paling mudah):** pasang kabel data → tekan **Allow** pada telefon (tandakan *Always allow*) → telefon muncul dalam **Peranti** dalam beberapa saat.
**WiFi (Android 11+):** PC dan telefon dalam rangkaian sama. **Pairing Center → ADB WiFi**:
1. Telefon: Wireless debugging → *Pair device with pairing code* → taip alamat dan kod 6 digit di Mirrorhub → *Pasangkan* (sekali).
2. Taip **IP:port** pada skrin utama Wireless debugging (bukan port pairing) → *Sambung*; atau *Imbas rangkaian*.
Jika WiFi terputus, Mirrorhub menyambung semula sendiri. Port Wireless debugging berubah apabila ia dimatikan/dihidupkan — Mirrorhub mencarinya melalui mDNS.

## D. Guna harian
| Mahu | Pergi ke | Cara |
|---|---|---|
| Lihat & kawal skrin | **Device Wall** (atau Peranti → *Buka & kawal*) | klik = ketik, seret = leret, tahan = tekan lama, papan kekunci = taip, ◀ ● ■ = Back/Home/Recents |
| Fokus satu telefon | Wall → ⤢ Mod Fokus | profil resolusi tinggi |
| Tangkap skrin / rakam | Peranti → *Tangkap skrin*; rakaman melalui API/Wall (tempoh dalam **Sistem → Keutamaan**) | fail di `Downloads`/`%APPDATA%\Mirrorhub\recordings` |
| Pasang APK | **Aplikasi & APK** | seret `.apk` → pilih telefon → Pasang |
| Hantar/ambil fail | **Fail** | seret & lepas; klik *Muat turun* |
| Urus peranti | **Peranti** | Edit (nama, kumpulan, tag, nota), Segarkan, Sambung semula, Lupakan |
| Automasi | **Automasi** | bina langkah → Jalankan (Batal bila-bila masa) |
| Backup | **Sistem → Cipta backup** | pulihkan dari senarai (berkuat kuasa selepas mula semula) |

## E. Kemas kini dan nyahpasang
Kemas kini: jalankan pemasang versi lebih baharu. Nyahpasang: *Settings → Apps*. Data kekal.

## F. Masalah?
`docs/TROUBLESHOOTING.md`. Pantas: **Sistem → Diagnostik**, atau `"%LOCALAPPDATA%\Programs\Mirrorhub\MirrorHub.exe" --diag`.
