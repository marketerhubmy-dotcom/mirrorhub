"""
Hardware validation tool.

    python -m app.tools.hwcheck                     # every authorized device, read-only checks
    python -m app.tools.hwcheck --serial ABC123     # one device
    python -m app.tools.hwcheck --seconds 30 --profile focus
    python -m app.tools.hwcheck --allow-input       # ALSO presses HOME and BACK on the phone (explicit opt-in)

Read-only by default: device facts, screenshot, ADB file listing of /sdcard (count only),
and a real scrcpy raw-stream session whose frames are counted (never stored).
Writes <data>/reports/hwcheck_<time>.json and .md with PASS/FAIL per check.

A PASS here means *this phone* did this *at this time*. It is evidence for docs/QA_MATRIX.md.
Static screens produce few frames (the encoder only emits on change) – the report says so
instead of calling a low fps a failure; use --seconds with something moving on screen for fps.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import time
from datetime import datetime

from app.core import runtime_paths as rp
from app.services import adb_client, device_info, device_ops
from app.services import adb_control
from app.services.scrcpy_stream import PROFILES, stream_manager


def _r(name, status, detail="", **extra):
    return {"check": name, "status": status, "detail": detail, **extra}


async def check_device(dev: adb_client.AdbDevice, seconds: float, profile: str, allow_input: bool) -> dict:
    out: dict = {"serial": dev.serial, "transport": dev.transport, "adb_state": dev.state, "results": []}
    res = out["results"]
    if dev.state != "device":
        res.append(_r("adb_state", "FAIL", f"state={dev.state}", hint="Authorize the PC on the phone / reconnect."))
        return out
    res.append(_r("adb_state", "PASS", "device"))

    # facts
    try:
        info = await device_info.fetch_info(dev.serial)
        out["info"] = info.to_dict()
        ok = bool(info.model and info.sdk and info.screen_w)
        res.append(_r("device_info", "PASS" if ok else "FAIL", f"{info.manufacturer} {info.model} Android {info.android_version} {info.screen_w}x{info.screen_h}"))
    except Exception as exc:
        res.append(_r("device_info", "FAIL", str(exc)))

    # screenshot
    t = time.perf_counter()
    try:
        png = await device_ops.screenshot(dev.serial)
        res.append(_r("screenshot", "PASS", f"{len(png)} bytes in {time.perf_counter() - t:.2f}s"))
    except Exception as exc:
        res.append(_r("screenshot", "FAIL", str(exc)))

    # file listing (count only)
    try:
        entries = await device_ops.list_dir(dev.serial, "/sdcard")
        res.append(_r("file_list", "PASS", f"{len(entries)} entries in /sdcard"))
    except Exception as exc:
        res.append(_r("file_list", "FAIL", str(exc)))

    # embedded stream
    did = f"hwcheck-{dev.serial}"
    sess, viewer = stream_manager.attach(did, dev.serial, profile)
    t0 = time.perf_counter()
    first = None
    frames = nbytes = keys = 0
    cpu0 = time.process_time()
    end = t0 + seconds + 12  # allow up to 12 s for startup
    stream_end = None
    try:
        while time.perf_counter() < (stream_end or end):
            try:
                au = await asyncio.wait_for(viewer.queue.get(), timeout=0.5)
            except asyncio.TimeoutError:
                if sess.state == "failed":
                    break
                continue
            if first is None:
                first = time.perf_counter() - t0
                stream_end = time.perf_counter() + seconds
            frames += 1
            nbytes += len(au)
            if b"\x00\x00\x01\x65" in au[:300]:
                keys += 1
    finally:
        cpu = time.process_time() - cpu0
        status = sess.status() if hasattr(sess, "status") else {}
        stream_manager.detach(sess, viewer)
        await stream_manager.stop_device(did)
    if first is None:
        res.append(_r("stream", "FAIL", f"no frame received (state={sess.state}, error={sess.error})",
                      hint="Check USB debugging (Security settings) on Xiaomi, and that no other app holds the screen capture."))
    else:
        active = max(seconds, 0.001)
        fps = frames / active
        res.append(_r("stream", "PASS", f"first frame {first:.2f}s, {frames} frames in {active:.0f}s ({fps:.1f} fps), "
                                        f"{nbytes * 8 / 1000 / active:.0f} kbit/s, {keys} keyframes, backend CPU {cpu:.2f}s",
                      first_frame_s=round(first, 2), frames=frames, fps=round(fps, 2), keyframes=keys,
                      kbps=round(nbytes * 8 / 1000 / active), backend_cpu_s=round(cpu, 2),
                      note="static screen → few frames is normal" if fps < 5 else ""))

    # input (explicit opt-in only)
    if allow_input:
        try:
            adb_control.nav(dev.serial, "home")
            await asyncio.sleep(0.5)
            adb_control.nav(dev.serial, "back")
            res.append(_r("input_home_back", "PASS", "HOME and BACK sent (verify visually on the phone)"))
        except Exception as exc:
            res.append(_r("input_home_back", "FAIL", str(exc)))
        finally:
            adb_control.close_shell(dev.serial)
    else:
        res.append(_r("input_home_back", "NOT TESTED", "run with --allow-input to press HOME/BACK"))
    return out


async def main_async(args) -> int:
    await adb_client.start_server()
    devices = await adb_client.list_devices()
    if args.serial:
        devices = [d for d in devices if d.serial == args.serial]
    if not devices:
        print("No devices found. Connect a phone (USB debugging ON) or use the Pairing Center.")
        return 2
    reports = []
    for d in devices:
        print(f"== {d.serial} ({d.transport}, {d.state})")
        rep = await check_device(d, args.seconds, args.profile, args.allow_input)
        for r in rep["results"]:
            print(f"  [{r['status']:<10}] {r['check']}: {r['detail']}")
        reports.append(rep)
    await stream_manager.stop_all()

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    d = rp.data_dir() / "reports"
    d.mkdir(exist_ok=True)
    (d / f"hwcheck_{stamp}.json").write_text(json.dumps(reports, indent=2, ensure_ascii=False), encoding="utf-8")
    md = [f"# Hardware check {stamp}\n"]
    for rep in reports:
        md.append(f"## {rep['serial']} ({rep['transport']})\n\n| Check | Status | Detail |\n|---|---|---|")
        md += [f"| {r['check']} | {r['status']} | {r['detail']} |" for r in rep["results"]]
        md.append("")
    (d / f"hwcheck_{stamp}.md").write_text("\n".join(md), encoding="utf-8")
    print(f"\nReport: {d / f'hwcheck_{stamp}.md'}")
    fails = sum(r["status"] == "FAIL" for rep in reports for r in rep["results"])
    return 1 if fails else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--serial")
    ap.add_argument("--seconds", type=float, default=15)
    ap.add_argument("--profile", choices=list(PROFILES), default="normal")
    ap.add_argument("--allow-input", action="store_true", help="also press HOME and BACK (changes what is on the phone screen)")
    return asyncio.run(main_async(ap.parse_args(argv)))


if __name__ == "__main__":
    raise SystemExit(main())
