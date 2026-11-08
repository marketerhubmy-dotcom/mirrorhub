# Seni bina: bersedia untuk lebih banyak telefon dan telefon maya (tanpa membina semula UI/DB)

Tiada Fasa 06–09 dimulakan. Dokumen ini merekod apa yang **sudah** menyokong pengembangan, dengan bukti ujian, dan apa yang belum.

| Keperluan | Mekanisme semasa | Bukti |
|---|---|---|
| Banyak peranti, satu UI | Setiap `Device` ada `device_id` unik; Wall, API dan WebSocket semuanya berkunci pada `device_id` (`/ws/video/{id}`, `/ws/control/{id}`, `/files/{id}`, `/apps/{id}`); arahan input membawa `device_id` dan ditolak jika tidak sepadan | `check_binding`, `test_control_ws_rejects_mismatched_device…`, simulasi Wall 2 peranti, HW 2 telefon (strim serentak) |
| Identiti stabil antara laluan | `hw_serial` (ro.serialno) = kunci; `adb_address` hanya laluan semasa (USB > WiFi > mDNS) | `test_same_phone_over_usb_and_wifi_is_one_device`; HW: 2 laluan → 1 baris |
| Skema DB tanpa ubah suai | `devices.transport` (`usb`/`wifi`/`emulator`), `state`, `tags`, `group_name`; lajur baharu ditambah automatik selepas backup (`REQUIRED_COLUMNS`) | `test_emulator_registers_as_a_normal_device…`, `test_data_migration` |
| Telefon maya | Emulator muncul sebagai `emulator-5554` dalam `adb devices`; `classify_transport` → `emulator`; didaftar, dipantau, distrim, dikawal melalui saluran yang sama; tidak pernah disambung semula melalui WiFi. UI memaparkan lencana "Maya" | ujian unit (bukan emulator sebenar — Fasa 06 belum dimulakan) |
| Sumber setiap sesi | satu sesi strim per `(device_id, profil)`; profil `thumb/normal/focus`; Wall memilih `thumb` apabila > 4 peranti; sesi dituai 5 s selepas penonton terakhir | `test_scrcpy_stream`, soak simulasi |
| Automasi banyak peranti | enjin selari per peranti, eksklusif per peranti, batal serentak | `test_automation_core` (45 ujian) |
| Kemas kini tanpa kehilangan data | data di `%APPDATA%`; migrasi skema selepas backup; restore berperingkat | `test_data_migration`, smoke pemasang |

## Belum (di luar V1 satu telefon)
- Pengurus kitaran hayat AVD (cipta/mula/henti) — `docs/PHASE06_PREP.md`.
- Kawalan melalui soket scrcpy (kini `adb shell input`, ±puluhan ms) — ADR-002/K19.
- Had sumber dikuatkuasakan untuk >4 strim fokus; ujian 4+ telefon fizikal (MULTI_DEVICE_READY).
- Capaian jauh/awan/pengesahan berbilang pengguna (Fasa 07–09; API sengaja loopback sahaja — ADR-004).
