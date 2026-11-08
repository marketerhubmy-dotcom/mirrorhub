"""adb_client: validation, parsing, result interpretation (no adb needed)."""
import pathlib
import sys

import pytest

from app.services import adb_client as ac
from app.services.adb_client import AdbError, AdbResult

DEVICES_OUT = """List of devices attached
R58M12ABCDE            device usb:1-2 product:a52qxx model:SM_A525F device:a52q transport_id:3
192.168.1.109:33587    device product:lancelot model:Redmi_9 device:lancelot transport_id:5
adb-R58M12ABCDE-xYz1._adb-tls-connect._tcp device product:a52qxx model:SM_A525F device:a52q transport_id:7
emulator-5554          device product:sdk_gphone model:sdk device:emu transport_id:1
0123456789ABCDEF       unauthorized usb:1-3 transport_id:9
ZY22          offline
ABC123         no permissions (user in plugdev group; see [http://developer.android.com/tools/device.html]) usb:1-4
* daemon started successfully
"""


def test_parse_devices_full():
    d = {x.serial: x for x in ac.parse_devices(DEVICES_OUT)}
    assert d["R58M12ABCDE"].transport == "usb" and d["R58M12ABCDE"].model == "SM A525F"
    assert d["192.168.1.109:33587"].transport == "wifi"
    assert d["adb-R58M12ABCDE-xYz1._adb-tls-connect._tcp"].transport == "wifi"
    assert d["emulator-5554"].transport == "emulator"
    assert d["0123456789ABCDEF"].state == "unauthorized"
    assert d["ZY22"].state == "offline"
    assert d["ABC123"].state == "no permissions"
    assert d["R58M12ABCDE"].transport_id == "3"
    assert len(d) == 7  # banner / daemon lines ignored


def test_parse_devices_empty():
    assert ac.parse_devices("List of devices attached\n\n") == []
    assert ac.parse_devices("") == []


@pytest.mark.parametrize("addr", ["192.168.1.5:37123", "10.0.0.2:5555", "phone.local:5555"])
def test_hostport_valid(addr):
    assert ac.validate_hostport(addr) == addr


@pytest.mark.parametrize("addr", ["", "192.168.1.5", "1.2.3.4:99999", "1.2.3.4:0", "999.1.1.1:5555",
                                  "1.2.3.4:5555; rm -rf /", "a b:5555", "-x:5555", "1.2.3.4:55\n55"])
def test_hostport_invalid(addr):
    with pytest.raises(AdbError):
        ac.validate_hostport(addr)


@pytest.mark.parametrize("code", ["123456", " 000000 "])
def test_pair_code_valid(code):
    assert ac.validate_pair_code(code) == code.strip()


@pytest.mark.parametrize("code", ["12345", "1234567", "abcdef", "", "12 456"])
def test_pair_code_invalid(code):
    with pytest.raises(AdbError):
        ac.validate_pair_code(code)


@pytest.mark.parametrize("serial", ["", "a b", "x;y", "a/b", "x" * 129, None, 5])
def test_serial_invalid(serial):
    with pytest.raises(AdbError):
        ac.validate_serial(serial)


def test_mdns_parse():
    out = ("List of discovered mdns services\n"
           "adb-R58M12ABCDE-xYz1\t_adb-tls-connect._tcp\t192.168.1.109:37001\n"
           "adb-R58M12ABCDE-pAir\t_adb-tls-pairing._tcp\t192.168.1.109:41999\n"
           "junk line\n")
    s = ac.parse_mdns(out)
    assert [(x.kind, x.address) for x in s] == [("connect", "192.168.1.109:37001"), ("pairing", "192.168.1.109:41999")]


@pytest.mark.parametrize("out,ok", [
    ("Successfully paired to 192.168.1.5:41999 [guid=adb-XXXX]", True),
    ("Failed: Wrong password or password and guid not matched", False),
    ("error: protocol fault (couldn't read status): connection reset", False),
    ("Enter pairing code: Unable to start pairing client.", False),
])
def test_interpret_pair(out, ok):
    good, msg = ac.interpret_pair(AdbResult(0, out))
    assert good is ok and msg


@pytest.mark.parametrize("out,ok", [
    ("connected to 192.168.1.5:5555", True),
    ("already connected to 192.168.1.5:5555", True),
    ("failed to connect to '192.168.1.5:5555': Connection refused", False),
    ("failed to connect to '1.2.3.4:5555': Connection timed out", False),
    ("failed to authenticate to 192.168.1.5:5555 unauthorized", False),
])
def test_interpret_connect(out, ok):
    good, msg = ac.interpret_connect(AdbResult(0, out))
    assert good is ok and msg


@pytest.mark.asyncio
async def test_pair_validates_before_running(monkeypatch):
    called = []

    async def fake(*a, **k):
        called.append(a)
        return AdbResult(0, "Successfully paired to x")

    monkeypatch.setattr(ac, "run_adb", fake)
    with pytest.raises(AdbError):
        await ac.pair("bad", "123456")
    with pytest.raises(AdbError):
        await ac.pair("1.2.3.4:5555", "12")
    assert called == []
    ok, _ = await ac.pair("1.2.3.4:5555", "123456")
    assert ok and called[0][:3] == ("pair", "1.2.3.4:5555", "123456")


@pytest.mark.asyncio
async def test_list_devices_error(monkeypatch):
    async def fake(*a, **k):
        return AdbResult(1, "", "boom")
    monkeypatch.setattr(ac, "run_adb", fake)
    with pytest.raises(AdbError):
        await ac.list_devices()


@pytest.mark.asyncio
async def test_run_adb_missing_binary(monkeypatch, tmp_path):
    monkeypatch.setattr(ac, "ADB", tmp_path / "nope.exe")
    with pytest.raises(ac.AdbMissing):
        await ac.run_adb("devices")


@pytest.mark.asyncio
async def test_run_adb_real_subprocess_and_timeout(monkeypatch):
    """Spawn a real process (python) in place of adb to exercise the runner and timeout."""
    monkeypatch.setattr(ac, "ADB", pathlib.Path(sys.executable))
    r = await ac.run_adb("-c", "print('hi')")
    assert r.rc == 0 and r.out.strip() == "hi"
    with pytest.raises(AdbError, match="tamat masa"):
        await ac.run_adb("-c", "import time; time.sleep(5)", timeout=0.3)


NL, TAB = chr(10), chr(9)
MD = ("List of discovered mdns services" + NL
      + "adb-HW1-abc" + TAB + "_adb-tls-connect._tcp" + TAB + "192.168.0.238:39927" + NL
      + "adb-HW2-def" + TAB + "_adb-tls-pairing._tcp" + TAB + "192.168.0.50:40000" + NL)


@pytest.mark.asyncio
async def test_resolve_wifi_target(monkeypatch):
    async def fake(*a, **k):
        return AdbResult(0, MD)

    monkeypatch.setattr(ac, "run_adb", fake)
    assert ac.is_mdns_serial("adb-HW1-abc._adb-tls-connect._tcp") and not ac.is_mdns_serial("1.2.3.4:5")
    assert await ac.resolve_wifi_target("adb-HW1-abc._adb-tls-connect._tcp") == "192.168.0.238:39927"
    assert await ac.resolve_wifi_target("adb-NOPE-x._adb-tls-connect._tcp") is None
    assert await ac.resolve_wifi_target("1.2.3.4:5555", hw_serial="HW1") == "192.168.0.238:39927"   # port rotated
    assert await ac.resolve_wifi_target("1.2.3.4:5555", hw_serial="HW9") == "1.2.3.4:5555"          # unchanged fallback
    assert await ac.resolve_wifi_target("USB123") is None                                           # USB is not reconnectable
