# KNOWN ISSUES (sahih pada 2026-11-08, sebelum pembaikan)

| ID | Isu | Cara reproduksi | Status |
|---|---|---|---|
| K1 | Shell injection melalui `input text` / `keyevent` | hantar teks `'; id; '` ke `/ws/control` | **DIBETULKAN** 2026-11-08 (44 ujian) |
| K2 | WS tanpa Origin/token; `device_id` boleh diteka | `new WebSocket('ws://127.0.0.1:8000/ws/control/<uuid5(IP:port)>')` dari mana-mana laman | **DIBETULKAN** 2026-11-08 (34 ujian) |
| K3 | `screenrecord` berhenti selepas ~180 s | tonton `/ws/video` > 3 min | Diganti oleh scrcpy raw stream (belum diuji pada telefon) |
| K4 | FK tidak dikuatkuasakan pada sesetengah laluan | `pytest tests/integration/test_database_foreign_keys.py` | Terbuka |
| K5 | 30 ujian gagal (22 lapuk) | `pytest` | Terbuka |
| K6 | DB di dalam folder app; arahan "delete mirrorhub.db" | `RELEASE_NOTES.md` | Terbuka |
| K7 | "Device Wall" bukan video | buka `/wall` | Terbuka |
| K8 | `config.host` = `0.0.0.0` (LAN exposure, Dev Mode) | `python run.py` sebelum pembaikan | **DIBETULKAN** |
| K9 | `/ws/stream`, `/ws/view` (laluan ejen Android / JPEG lama) tidak diaudit | — | Terbuka |
| K10 | Port 8000 tetap; jika dipakai, app tidak bermula dengan mesej jelas | — | Terbuka |
