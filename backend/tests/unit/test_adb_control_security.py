"""Security tests for input control (docs/AUDIT.md S1/S3). No hardware needed."""
import pytest

from app.services import adb_control as ac
from app.services.adb_control import ControlError
from app.websocket import control as ctl


@pytest.fixture
def sent(monkeypatch):
    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(ac, "_send", lambda addr, cmd: calls.append((addr, cmd)))
    monkeypatch.setattr(ac, "get_screen_size", lambda addr: (1080, 2400))
    return calls


def test_text_injection_is_quoted(sent):
    ac.input_text("1.2.3.4:5555", "'; reboot; echo '")
    (_, cmd), = sent
    # Whole argument is one single-quoted word; the embedded quotes are escaped.
    assert cmd == "input text ''\\'';%sreboot;%secho%s'\\'''"
    # Parse it back the way sh would: exactly one word after `input text`.
    import shlex
    assert shlex.split(cmd) == ["input", "text", "';%sreboot;%secho%s'"]


def test_text_replaces_space_and_keeps_shell_metachars_literal(sent):
    ac.input_text("dev", "a b $(id) `x` & | > ;")
    (_, cmd), = sent
    assert cmd == "input text 'a%sb%s$(id)%s`x`%s&%s|%s>%s;'"


@pytest.mark.parametrize("bad", ["a\nreboot", "a\rb", "x\x00y", "\x1b[31m", "x" * 501])
def test_text_rejects_control_chars_and_overlong(sent, bad):
    with pytest.raises(ControlError):
        ac.input_text("dev", bad)
    assert sent == []


@pytest.mark.parametrize("bad", ["4; reboot", "KEYCODE_HOME; id", "keycode_home", "-1", 401, True, None, 1.5, "$(id)"])
def test_keycode_rejects_injection(sent, bad):
    with pytest.raises(ControlError):
        ac.keyevent("dev", bad)
    assert sent == []


@pytest.mark.parametrize("ok,expected", [(4, "4"), ("66", "66"), ("KEYCODE_ENTER", "KEYCODE_ENTER")])
def test_keycode_accepts_valid(sent, ok, expected):
    ac.keyevent("dev", ok)
    assert sent == [("dev", f"input keyevent {expected}")]


@pytest.mark.parametrize("bad", [-0.1, 1.01, float("nan"), float("inf"), "0.5", None, True])
def test_coordinates_validated(sent, bad):
    with pytest.raises(ControlError):
        ac.tap("dev", bad, 0.5)
    assert sent == []


def test_tap_maps_relative_to_pixels(sent):
    ac.tap("dev", 0.5, 1.0)
    assert sent == [("dev", f"input tap {int(0.5 * 1079)} 2399")]


@pytest.mark.parametrize("serial", ["", "a b", "x;y", "a\nb", "$(id)", "a" * 200, None])
def test_serial_validated(serial):
    with pytest.raises(ControlError):
        ac.validate_serial(serial)


def test_unknown_nav_rejected(sent):
    with pytest.raises(ControlError):
        ac.nav("dev", "power_off")


# ── WebSocket binding ─────────────────────────────────────────────────────────

def test_binding_rejects_other_device_id():
    with pytest.raises(ControlError):
        ctl.check_binding("A", {"type": "tap", "x": 0.1, "y": 0.1, "device_id": "B"})


def test_binding_accepts_matching_or_absent_id():
    assert ctl.check_binding("A", {"type": "nav", "action": "home", "device_id": "A"})
    assert ctl.check_binding("A", {"type": "nav", "action": "home"})


@pytest.mark.parametrize("bad", [[], "x", None, {"type": "shell", "cmd": "id"}, {}])
def test_binding_rejects_bad_payload(bad):
    with pytest.raises(ControlError):
        ctl.check_binding("A", bad)


def test_dispatch_missing_field_is_control_error(sent):
    with pytest.raises(ControlError):
        ctl.dispatch_adb("dev", {"type": "tap", "x": 0.1})
    assert sent == []


def test_dispatch_routes_only_to_given_address(sent):
    ctl.dispatch_adb("phone-A:5555", {"type": "nav", "action": "back"})
    ctl.dispatch_adb("phone-B:5555", {"type": "nav", "action": "home"})
    assert sent == [
        ("phone-A:5555", "input keyevent KEYCODE_BACK"),
        ("phone-B:5555", "input keyevent KEYCODE_HOME"),
    ]
