from app.services import device_info as di

BATT = """Current Battery Service state:
  AC powered: false
  USB powered: true
  Wireless powered: false
  status: 2
  health: 2
  present: true
  level: 87
  scale: 100
  temperature: 312
"""
DF = """Filesystem      1K-blocks     Used Available Use% Mounted on
/dev/block/dm-9 111111168 33333333  77777835  31% /data
"""


def test_battery():
    assert di.parse_battery(BATT) == (87, True, 31.2)
    assert di.parse_battery("garbage") == (-1, False, None)


def test_battery_not_charging():
    lvl, ch, _ = di.parse_battery("  AC powered: false\n  USB powered: false\n  status: 3\n  level: 12\n")
    assert (lvl, ch) == (12, False)


def test_df():
    assert di.parse_df(DF) == (108507, 75954)
    assert di.parse_df("") == (0, 0)


def test_wm_override_wins():
    assert di.parse_wm_size("Physical size: 1080x2400\nOverride size: 720x1600") == (720, 1600)
    assert di.parse_wm_size("Physical size: 1080x2400") == (1080, 2400)
    assert di.parse_wm_size("") == (0, 0)


def test_density_and_ip():
    assert di.parse_density("Physical density: 420") == 420
    assert di.parse_density("Physical density: 420\nOverride density: 320") == 320
    assert di.parse_ip("    inet 192.168.1.109/24 brd 192.168.1.255 scope global wlan0") == "192.168.1.109"
    assert di.parse_ip("") == ""


def test_parse_info_full_and_missing_sections():
    out = di.SEP.join(["SM-A525F\n", "samsung\n", "13\n", "33\n", "R58M12ABCDE\n", "a52qxx\n",
                       BATT, DF, "Physical size: 1080x2400\n", "Physical density: 420\n",
                       "inet 192.168.1.109/24 scope global wlan0\n"])
    i = di.parse_info(out)
    assert (i.model, i.manufacturer, i.android_version, i.sdk, i.hw_serial) == ("SM-A525F", "samsung", "13", 33, "R58M12ABCDE")
    assert (i.battery, i.charging, i.screen_w, i.screen_h, i.wifi_ip) == (87, True, 1080, 2400, "192.168.1.109")
    assert i.storage_total_mb == 108507
    short = di.parse_info("only-model")
    assert short.model == "only-model" and short.battery == -1 and short.sdk == 0


def test_script_has_expected_separators():
    assert di._SCRIPT.count(di.SEP) == 10
