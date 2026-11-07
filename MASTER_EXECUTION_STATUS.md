# MASTER EXECUTION STATUS

Dikemas kini: 2026-11-08 · Branch: `dev/desktop-v1` (baseline `f0688a7` di `main`) · Remote GitHub: kosong, **belum di-push**.

| Fasa | Status | Catatan |
|---|---|---|
| 00 Audit | **SIAP (docs)** | `docs/AUDIT.md`, `DECISIONS.md`, `QA_MATRIX.md`, `FEATURE_BACKLOG.md`, `KNOWN_ISSUES.md` |
| 00 PoC 2-stream embedded | **KOD SIAP; simulasi PASS; hardware NOT TESTED** | 0 telefon. Pelayar+hub+kawalan disahkan dengan harness; pelancaran scrcpy-server 4.0 pada peranti belum |
| 01 (sebahagian) | Keselamatan loopback SIAP; Device Wall embedded + DevicePage SIAP | data→AppData belum |
| 01 Desktop foundation | Belum mula | data → `%APPDATA%`, token/Origin |
| 02 Multi-phone mirroring | Belum mula | bergantung PoC |
| 03–05 | Belum mula | pemasang perlu PyInstaller + Inno Setup |
| 06–09 | Belum mula / disekat | tiada JDK/Android SDK; cloud perlu kelulusan |

## Seterusnya
1. **(perlu telefon)** Sahkan pelancaran scrcpy-server 4.0 (`raw_stream`) pada 1 telefon, kemudian 2; rekod FPS/CPU/RAM/latency. Jika server menolak `raw_stream`, gunakan mod framing (ADR-002).
2. Data pengguna ke `%APPDATA%\Mirrorhub` (ADR-005) + migrasi dengan backup.
3. Pairing UI (WiFi pairing code, USB hot-plug), device manager, APK/fail.
4. Bersihkan 30 ujian lama; betulkan FK (K4).
5. Pemasang: PyInstaller (pip, venv) + Inno Setup (**perlu kelulusan pasang**), semakan lesen binari.

## Blocker luaran
- Sambung 2 atau lebih telefon Android (USB debugging dibenarkan) untuk gate PoC/Fasa 02.
- Kelulusan pemilik: push ke GitHub (repo kosong); memasang Inno Setup.
