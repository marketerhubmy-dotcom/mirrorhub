# Panduan Pengguna Mirrorhub Desktop V1

> Mula pantas pemasangan dan sambungan: `docs/SETUP_GUIDE.md`. Penyelesaian masalah: `docs/TROUBLESHOOTING.md`.

## 1. Pemasangan
1. Jalankan `Mirrorhub-Setup-1.0.0.exe` (tidak perlu hak admin; dipasang untuk pengguna semasa).
2. Pilih folder (lalai: `%LOCALAPPDATA%\Programs\Mirrorhub`). Tandakan *Create a Desktop shortcut* jika mahu.
3. Selesai → **Launch Mirrorhub**. Python, Node atau Rust **tidak** diperlukan; ADB dan pelayan skrin disertakan.
4. Jika Windows anda tiada *Microsoft Edge WebView2 Runtime* (jarang pada Windows 10/11), Mirrorhub dibuka dalam pelayar lalai sebagai ganti.

Data anda (pangkalan data, muat naik, backup, log) berada di `%APPDATA%\Mirrorhub`. Menyahpasang **tidak** memadam folder ini.
Jika anda pernah menjalankan versi sumber (`backend\mirrorhub.db`), salin fail itu ke `%APPDATA%\Mirrorhub\` sebelum membuka Mirrorhub kali pertama — versi sumber menyalinnya sendiri secara automatik.

## 2. Sediakan telefon
1. Settings → About phone → ketuk **Build number** 7 kali.
2. Developer options → hidupkan **USB debugging** dan/atau **Wireless debugging** (Android 11+).
3. Xiaomi/Redmi/Poco: hidupkan juga **Install via USB** dan **USB debugging (Security settings)**.

## 3. Sambung telefon (Pairing Center)
**USB** — sambung dengan kabel data, tekan *Allow* pada telefon (tandakan "Always allow"). Telefon muncul sendiri dalam beberapa saat.
**ADB WiFi** — tab *ADB WiFi*:
1. Pada telefon: Wireless debugging → **Pair device with pairing code**. Taip alamat `IP:port` dan kod 6 digit → *Pasangkan* (sekali sahaja).
2. Masukkan **IP:port pada skrin utama Wireless debugging** (port berbeza daripada port pairing) → *Sambung*. Atau guna *Imbas rangkaian* untuk penemuan automatik.
Jika sambungan WiFi terputus, Mirrorhub cuba menyambung semula (2→5→10→20→40→60 saat). Port Wireless debugging berubah setiap kali ia dihidupkan semula; jika begitu, sambung dengan port baharu.

## 4. Peranti (pengurus peranti)
Kad setiap telefon: status (Online / Perlu kebenaran / Menyambung semula / Offline), model, Android, bateri, storan, USB/WiFi. Tindakan: *Buka & kawal*, *Tangkap skrin*, *Apl*, *Fail*, *Segarkan*, *Sambung semula*, *Edit* (nama, kumpulan, tag, nota), *Lupakan* (memadam rekod dalam Mirrorhub sahaja; telefon tidak terjejas).
Telefon yang sama melalui USB dan WiFi dikenali sebagai **satu** peranti (USB diutamakan; jika kabel dicabut, WiFi diambil alih).

## 5. Device Wall
Semua skrin telefon dalam satu halaman (strim H.264 terus ke tetingkap — bukan tetingkap berasingan).
- Susun atur Auto/1/2/4/9, **Fokus** (satu besar + lain kecil), **Jeda** per telefon atau semua, carian, *Termasuk offline*.
- Klik/seret/tahan pada skrin = ketik/leret/tekan lama pada telefon itu sahaja. Kekunci papan kekunci menaip ke telefon yang difokus. Butang ◀ ● ■ = Back / Home / Recents.
- Lebih 4 peranti → profil thumbnail (resolusi/FPS rendah) untuk jimat CPU; satu peranti Fokus → resolusi tinggi.
- Skrin statik menghasilkan sedikit bingkai (encoder hanya menghantar apabila skrin berubah) — "0 fps" pada skrin statik adalah normal.

## 6. Aplikasi & APK
Seret `.apk` ke pustaka, pilih satu/banyak telefon, *Pasang*. Keputusan dipaparkan **per telefon** dengan sebab kegagalan dalam Bahasa Malaysia (storan penuh, downgrade, tandatangan tidak sepadan, sekatan USB Xiaomi …). Senarai aplikasi terpasang: Buka / Henti / Kosongkan data / Nyahpasang (dengan pengesahan). APK berpecah (`.apks`/`.xapk`) belum disokong.

## 7. Pengurus Fail
Layari storan telefon (`/sdcard` dsb.), muat naik (seret & lepas, banyak fail), muat turun, folder baharu, namakan semula, padam (pengesahan; folder sistem/akar dilindungi).

## 8. Automasi
Bina urutan: buka/tutup aplikasi, ketik, leret, taip, kekunci, navigasi, tunggu, **ketik/tunggu teks pada skrin** (uiautomator), tangkap skrin. Setiap langkah boleh *cuba semula*, ada *had masa* dan *teruskan jika gagal*. Pilih peranti → *Jalankan*; telefon berjalan serentak, satu kegagalan tidak menghentikan yang lain; **Batal** menghentikan serta-merta. Satu telefon hanya boleh menjalankan satu automasi pada satu masa. Templat disimpan dalam pelayar/tetingkap ini. **Semak urutan pada satu telefon dahulu** — automasi menggerakkan telefon sebenar.
Modul lama (TikTok / YT Create / AI) ada di *Lanjutan*.

## 8b. Prestasi (sidebar "Prestasi")
- **Kad ringkasan**: peranti bersambung/terputus/perlu kebenaran, strim aktif, FPS purata, CPU/RAM **PC** berasingan daripada CPU/RAM **proses Mirrorhub**, reconnect, kesihatan keseluruhan.
- **Graf langsung** (CPU, RAM, FPS, strim, reconnect, soket) dengan sejarah 5 min / 15 min / 1 jam / sesi. Sejarah hanya dalam memori; hilang bila aplikasi ditutup.
- **Jadual per peranti**: FPS, resolusi, bitrate, masa mula, reconnect, bateri, ralat terakhir. Nilai yang tidak boleh diukur dipaparkan **N/A + sebab** (bukan angka rekaan).
- **Kesihatan**: Sihat / Terjejas / Menyambung semula / Terputus / Perlu kebenaran. Telefon yang skrinnya statik (idle, 0 fps) dianggap **sihat**, bukan rosak.
- **Amaran**: RAM tinggi, CPU berterusan tinggi, gelung reconnect, strim tersangkut, pertumbuhan memori, terlalu banyak strim. Ambang boleh diubah dalam tetapan; lihat `docs/PERFORMANCE_DASHBOARD.md`.
- **Diagnostik**: butang *Salin laporan*, *Eksport JSON/CSV* — tiada kata laluan/kunci/kandungan skrin; IP dan nama pengguna Windows dimasking.

## 9. Sistem
Diagnostik persekitaran, lokasi data, **Cipta backup**, **Pulihkan** (dijadualkan; dilaksanakan apabila aplikasi dibuka semula, dengan backup keselamatan keadaan semasa).

## 10. Keselamatan
API hanya mendengar pada `127.0.0.1` dan menolak halaman web lain (Origin/Host). Tiada akaun, kunci API atau awan diperlukan. Kunci OpenAI (pilihan, modul lanjutan) diletakkan dalam `%APPDATA%\Mirrorhub\.env` sebagai `OPENAI_API_KEY=...`.
