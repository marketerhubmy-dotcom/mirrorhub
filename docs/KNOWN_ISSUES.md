# KNOWN ISSUES (sahih pada 2026-11-08, sebelum pembaikan)

| ID | Isu | Cara reproduksi | Status |
|---|---|---|---|
| K1 | Shell injection melalui `input text` / `keyevent` | hantar teks `'; id; '` ke `/ws/control` | Terbuka (S1) |
| K2 | WS tanpa Origin/token; `device_id` boleh diteka | `new WebSocket('ws://127.0.0.1:8000/ws/control/<uuid5(IP:port)>')` dari mana-mana laman | Terbuka (S2) |
| K3 | `screenrecord` berhenti selepas ~180 s | tonton `/ws/video` > 3 min | Akan diganti (ADR-002) |
| K4 | FK tidak dikuatkuasakan pada sesetengah laluan | `pytest tests/integration/test_database_foreign_keys.py` | Terbuka |
| K5 | 30 ujian gagal (22 lapuk) | `pytest` | Terbuka |
| K6 | DB di dalam folder app; arahan "delete mirrorhub.db" | `RELEASE_NOTES.md` | Terbuka |
| K7 | "Device Wall" bukan video | buka `/wall` | Terbuka |
