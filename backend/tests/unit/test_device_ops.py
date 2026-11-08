"""device_ops: validation, parsing, command construction. adb is faked; nothing touches a phone."""
import pytest

from app.services import device_ops as ops
from app.services.adb_client import AdbError, AdbResult

LS_NEW = """total 24
drwxrwx--x 2 u0_a123 media_rw   4096 2024-05-04 10:11 DCIM
drwxrwx--x 4 u0_a123 media_rw   4096 2024-05-04 10:11 Download
-rw-rw---- 1 u0_a123 media_rw 123456 2024-06-01 09:30 my photo (1).jpg
lrwxrwxrwx 1 root    root         21 2024-01-01 00:00 sdcard -> /storage/self/primary
-rw-rw---- 1 u0_a123 media_rw      0 2024-06-01 09:30 z.txt
drwxr-xr-x 2 root root 4096 2024-01-01 00:00 .
drwxr-xr-x 2 root root 4096 2024-01-01 00:00 ..
"""
LS_OLD = """drwxrwxr-x root     sdcard_rw          2015-01-01 12:00 Android
-rw-rw---- root     sdcard_rw   123456 Jan  5 12:00 old.txt
"""


class Fake:
    def __init__(self, results):
        self.calls = []
        self.results = list(results)

    async def __call__(self, *args, serial=None, timeout=15, **kw):
        self.calls.append((args, serial))
        return self.results.pop(0) if self.results else AdbResult(0, "")


def patch(monkeypatch, *results):
    f = Fake(results)
    monkeypatch.setattr(ops, "run_adb", f)
    return f


# ── validation ──
@pytest.mark.parametrize("pkg", ["com.tiktok.android", "org.a.b_c", "com.Foo.Bar2"])
def test_pkg_ok(pkg):
    assert ops.validate_package(pkg) == pkg


@pytest.mark.parametrize("pkg", ["", "nodot", "com.x;rm -rf /", "com..x", "1com.x", "com.x y", "a" * 300 + ".b", None])
def test_pkg_bad(pkg):
    with pytest.raises(AdbError):
        ops.validate_package(pkg)


@pytest.mark.parametrize("p", ["/sdcard", "/sdcard/Download/a b.txt", "/data/local/tmp/"])
def test_remote_path_ok(p):
    assert ops.validate_remote_path(p).startswith("/")


@pytest.mark.parametrize("p", ["sdcard", "", "/sdcard/../data", "/a\nb", "/a\x00b", "/" + "a" * 1100, None])
def test_remote_path_bad(p):
    with pytest.raises(AdbError):
        ops.validate_remote_path(p)


@pytest.mark.parametrize("n", ["", ".", "..", "a/b", "a\nb", "x" * 300])
def test_remote_name_bad(n):
    with pytest.raises(AdbError):
        ops.validate_remote_name(n)


@pytest.mark.parametrize("n", ["app.apk", "My App (1).apk", "a-b_c+d.APK"])
def test_apk_name_ok(n):
    assert ops.validate_apk_name(n) == n


@pytest.mark.parametrize("n", ["a.txt", "../a.apk", "a/b.apk", "a\\b.apk", ".apk", "x;y.apk"])
def test_apk_name_bad(n):
    with pytest.raises(AdbError):
        ops.validate_apk_name(n)


@pytest.mark.parametrize("p", ["/", "/sdcard", "/sdcard/", "/storage/emulated/0", "/data", "/system", "/sdcard/DCIM"])
def test_protected(p):
    with pytest.raises(AdbError):
        ops.assert_not_protected(p)


def test_children_of_protected_allowed():
    ops.assert_not_protected("/sdcard/Download/x")


# ── parsing ──
def test_parse_ls_new_format():
    e = {x.name: x for x in ops.parse_ls(LS_NEW)}
    assert set(e) == {"DCIM", "Download", "my photo (1).jpg", "sdcard", "z.txt"}
    assert e["DCIM"].is_dir and not e["z.txt"].is_dir
    assert e["my photo (1).jpg"].size == 123456 and e["my photo (1).jpg"].modified == "2024-06-01 09:30"
    assert e["sdcard"].link_to == "/storage/self/primary"
    order = [x.name for x in ops.parse_ls(LS_NEW)]
    assert order[:2] == ["DCIM", "Download"]          # dirs first


def test_parse_ls_old_format():
    e = {x.name: x for x in ops.parse_ls(LS_OLD)}
    assert e["Android"].is_dir and e["old.txt"].size == 123456


def test_parse_packages():
    assert ops.parse_packages("package:com.b\npackage:com.a\njunk\n") == ["com.a", "com.b"]


@pytest.mark.parametrize("out,ok,frag", [
    ("Performing Streamed Install\nSuccess\n", True, "berjaya"),
    ("adb: failed to install x.apk: Failure [INSTALL_FAILED_VERSION_DOWNGRADE]", False, "downgrade"),
    ("Failure [INSTALL_FAILED_USER_RESTRICTED: Install canceled by user]", False, "USB"),
    ("Failure [INSTALL_FAILED_SOMETHING_NEW]", False, "SOMETHING_NEW"),
    ("error: device offline", False, "terputus"),
])
def test_interpret_install(out, ok, frag):
    good, msg = ops.interpret_install(AdbResult(0 if ok else 1, out))
    assert good is ok and frag.lower() in msg.lower()


# ── command construction ──
@pytest.mark.asyncio
async def test_install_flags_and_missing_file(monkeypatch, tmp_path):
    f = patch(monkeypatch, AdbResult(0, "Success"))
    apk = tmp_path / "a.apk"
    apk.write_bytes(b"x")
    ok, _ = await ops.install_apk("SER", apk, downgrade=True)
    assert ok and f.calls[0][0] == ("install", "-r", "-g", "-d", str(apk)) and f.calls[0][1] == "SER"
    with pytest.raises(AdbError):
        await ops.install_apk("SER", tmp_path / "missing.apk")
    txt = tmp_path / "a.txt"
    txt.write_text("x")
    with pytest.raises(AdbError):
        await ops.install_apk("SER", txt)


@pytest.mark.asyncio
async def test_uninstall_launch_stop_clear(monkeypatch):
    f = patch(monkeypatch, AdbResult(0, "Success"), AdbResult(0, "Events injected: 1"),
              AdbResult(0, ""), AdbResult(0, "Success"))
    assert (await ops.uninstall("S", "com.a.b", keep_data=True))[0]
    assert (await ops.launch("S", "com.a.b"))[0]
    assert (await ops.force_stop("S", "com.a.b"))[0]
    assert (await ops.clear_data("S", "com.a.b"))[0]
    assert f.calls[0][0] == ("shell", "pm", "uninstall", "-k", "com.a.b")
    assert f.calls[1][0][:4] == ("shell", "monkey", "-p", "com.a.b")
    with pytest.raises(AdbError):
        await ops.uninstall("S", "bad name; rm")
    assert len(f.calls) == 4  # the invalid one never reached adb


@pytest.mark.asyncio
async def test_launch_no_activity(monkeypatch):
    patch(monkeypatch, AdbResult(0, "** No activities found to run, monkey aborted."))
    ok, _ = await ops.launch("S", "com.a.b")
    assert ok is False


@pytest.mark.asyncio
async def test_list_dir_quotes_path_and_maps_errors(monkeypatch):
    f = patch(monkeypatch, AdbResult(0, LS_NEW))
    ents = await ops.list_dir("S", "/sdcard/it's here")
    assert len(ents) == 5
    cmd = f.calls[0][0][1]
    assert cmd == "ls -lA '/sdcard/it'\\''s here'/"
    patch(monkeypatch, AdbResult(1, "", "ls: /x/: No such file or directory"))
    with pytest.raises(AdbError, match="tidak wujud"):
        await ops.list_dir("S", "/x")
    patch(monkeypatch, AdbResult(1, "", "ls: /data/: Permission denied"))
    with pytest.raises(AdbError, match="Akses ditolak"):
        await ops.list_dir("S", "/data")


@pytest.mark.asyncio
async def test_delete_and_rename_guard_and_quote(monkeypatch):
    f = patch(monkeypatch)
    with pytest.raises(AdbError):
        await ops.delete_path("S", "/sdcard")
    with pytest.raises(AdbError):
        await ops.delete_path("S", "/")
    with pytest.raises(AdbError):
        await ops.rename_path("S", "/sdcard/DCIM", "x")
    assert f.calls == []
    await ops.delete_path("S", "/sdcard/Download/a b; rm -rf x")
    assert f.calls[0][0][1] == "rm -rf '/sdcard/Download/a b; rm -rf x'"
    dest = await ops.rename_path("S", "/sdcard/Download/a.txt", "b.txt")
    assert dest == "/sdcard/Download/b.txt"
    assert f.calls[1][0][1] == "mv '/sdcard/Download/a.txt' '/sdcard/Download/b.txt'"
    with pytest.raises(AdbError):
        await ops.rename_path("S", "/sdcard/Download/a.txt", "../evil")


@pytest.mark.asyncio
async def test_mkdir_errors_surface(monkeypatch):
    patch(monkeypatch, AdbResult(1, "", "mkdir: '/x': Read-only file system"))
    with pytest.raises(AdbError, match="Read-only"):
        await ops.make_dir("S", "/x/y")


@pytest.mark.asyncio
async def test_push_pull(monkeypatch, tmp_path):
    f = patch(monkeypatch, AdbResult(0, "x.jpg: 1 file pushed, 0 skipped. 5 MB/s"), AdbResult(0, ""),
              AdbResult(0, "/sdcard/a.txt: 1 file pulled, 0 skipped."))
    src = tmp_path / "x.jpg"
    src.write_bytes(b"1")
    dest = await ops.push_file("S", src, "/sdcard/Pictures")
    assert dest == "/sdcard/Pictures/x.jpg"
    assert f.calls[0][0] == ("push", str(src), "/sdcard/Pictures/x.jpg")
    assert f.calls[1][0][:4] == ("shell", "am", "broadcast", "-a")        # media scan for images
    out = await ops.pull_file("S", "/sdcard/a.txt", tmp_path / "sub" / "a.txt")
    assert out.parent.is_dir()
    with pytest.raises(AdbError):
        await ops.push_file("S", tmp_path / "nope", "/sdcard")


@pytest.mark.asyncio
async def test_push_failure(monkeypatch, tmp_path):
    patch(monkeypatch, AdbResult(1, "", "adb: error: failed to copy: No space left on device"))
    src = tmp_path / "x.bin"
    src.write_bytes(b"1")
    with pytest.raises(AdbError, match="No space"):
        await ops.push_file("S", src, "/sdcard")


@pytest.mark.asyncio
async def test_screenshot_validates_png(monkeypatch):
    async def good(*a, **k):
        return 0, ops.PNG_MAGIC + b"data", ""

    async def bad(*a, **k):
        return 0, b"not png", ""

    monkeypatch.setattr(ops, "run_adb_bytes", good)
    assert (await ops.screenshot("S")).startswith(ops.PNG_MAGIC)
    monkeypatch.setattr(ops, "run_adb_bytes", bad)
    with pytest.raises(AdbError):
        await ops.screenshot("S")


# ── input / screen probes (real Redmi/HyperOS output captured 2026-11-08) ──
SEC = "Exception occurred while executing 'keyevent':" + chr(10) + "java.lang.SecurityException: Injecting input events requires the caller (or the source of the instrumentation, if any) to have the INJECT_EVENTS permission."


def test_interpret_input_probe():
    assert ops.interpret_input_probe(AdbResult(0, "", SEC))[0] == "blocked"
    assert "Security settings" in ops.interpret_input_probe(AdbResult(0, "", SEC))[1]
    assert ops.interpret_input_probe(AdbResult(0, ""))[0] == "ok"
    assert ops.interpret_input_probe(AdbResult(1, "", "error: closed"))[0] == "unknown"


@pytest.mark.asyncio
async def test_input_state_and_screen_awake(monkeypatch):
    f = patch(monkeypatch, AdbResult(0, "", SEC), AdbResult(0, "  mWakefulness=Dozing"),
              AdbResult(0, "  mWakefulness=Awake"), AdbResult(0, ""))
    assert (await ops.input_state("S"))[0] == "blocked"
    assert f.calls[0][0] == ("shell", "input", "keyevent", "KEYCODE_UNKNOWN")
    assert await ops.screen_awake("S") is False
    assert await ops.screen_awake("S") is True
    assert await ops.screen_awake("S") is None
