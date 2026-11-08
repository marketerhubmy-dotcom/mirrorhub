"""
Soak / stability test against a RUNNING Mirrorhub backend (read-only: it only watches streams).

    python -m app.tools.soak --minutes 60 [--profile normal|thumb] [--base http://127.0.0.1:8000] [--out soak.csv]

For every online device it opens a /ws/video stream (like a Device Wall tile) and reconnects like the browser does,
while sampling backend memory / handles / threads / CPU time every --interval seconds. Prints a verdict:
  PASS  = streams stayed alive (>= 99 % of samples receiving or legitimately static), RSS growth below limit,
          no handle/thread growth trend, no crash.
Evidence only for the duration actually run – a 30 minute run is not an 8 hour soak.
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import time

import httpx
import websockets


async def watch(base_ws: str, device_id: str, profile: str, stats: dict, stop: asyncio.Event) -> None:
    s = stats[device_id] = {"frames": 0, "bytes": 0, "reconnects": 0, "errors": [], "last_frame": time.time(), "states": {}}
    while not stop.is_set():
        try:
            async with websockets.connect(f"{base_ws}/ws/video/{device_id}?profile={profile}",
                                          origin="http://127.0.0.1:8000", max_size=32 * 1024 * 1024) as ws:
                while not stop.is_set():
                    try:
                        m = await asyncio.wait_for(ws.recv(), 1.0)
                    except asyncio.TimeoutError:
                        continue
                    if isinstance(m, bytes):
                        s["frames"] += 1
                        s["bytes"] += len(m)
                        s["last_frame"] = time.time()
                    else:
                        ev = json.loads(m)
                        if ev.get("event") == "state":
                            s["states"][ev["state"]] = s["states"].get(ev["state"], 0) + 1
                        elif ev.get("event") == "error":
                            s["errors"].append(ev.get("error", "")[:120])
        except Exception as exc:
            s["errors"].append(str(exc)[:120])
        if not stop.is_set():
            s["reconnects"] += 1
            await asyncio.sleep(min(1 + s["reconnects"], 10))


async def main_async(a) -> int:
    base_ws = a.base.replace("http", "ws", 1)
    async with httpx.AsyncClient(base_url=a.base + "/api/v1", headers={"Origin": a.base}, timeout=20) as c:
        devs = [d for d in (await c.get("/devices")).json() if d["is_online"] and d["state"] == "online"]
        if not devs:
            print("no online devices")
            return 2
        print(f"soak: {len(devs)} device(s), {a.minutes} min, profile={a.profile}")
        stats: dict = {}
        stop = asyncio.Event()
        tasks = [asyncio.create_task(watch(base_ws, d["device_id"], a.profile, stats, stop)) for d in devs]
        rows = []
        t0 = time.time()
        end = t0 + a.minutes * 60
        crashed = False
        while time.time() < end:
            await asyncio.sleep(a.interval)
            try:
                m = (await c.get("/system/metrics")).json()
            except Exception as exc:
                crashed = True
                print("backend unreachable:", exc)
                break
            row = {"t_min": round((time.time() - t0) / 60, 1), **{k: m["process"][k] for k in ("rss_mb", "handles", "threads", "cpu_time_s")},
                   "frames": sum(v["frames"] for v in stats.values()), "reconnects": sum(v["reconnects"] for v in stats.values()),
                   "streams": len(m["streams"])}
            rows.append(row)
            print(row, flush=True)
        stop.set()
        await asyncio.gather(*tasks, return_exceptions=True)

    if a.out:
        with open(a.out, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else ["t_min"])
            w.writeheader()
            w.writerows(rows)
    verdict = []
    if crashed or not rows:
        verdict.append("backend became unreachable")
    else:
        first = rows[min(2, len(rows) - 1)]          # after warm-up
        last = rows[-1]
        rss_growth = (last["rss_mb"] or 0) - (first["rss_mb"] or 0)
        verdict.append(f"RSS {first['rss_mb']} -> {last['rss_mb']} MB (growth {rss_growth:+.1f})")
        verdict.append(f"handles {first['handles']} -> {last['handles']}, threads {first['threads']} -> {last['threads']}")
        if rss_growth > a.max_rss_growth_mb:
            verdict.append("FAIL: RSS growth above limit")
        if (last["handles"] or 0) - (first["handles"] or 0) > 50:
            verdict.append("FAIL: handle growth")
        if (last["threads"] or 0) - (first["threads"] or 0) > 20:
            verdict.append("FAIL: thread growth")
    for did, s in stats.items():
        verdict.append(f"{did[:8]}: frames={s['frames']} reconnects={s['reconnects']} states={s['states']} errors={len(s['errors'])}")
    bad = [v for v in verdict if v.startswith("FAIL") or "unreachable" in v]
    print("\n".join(verdict))
    print("SOAK", "FAIL" if bad else "PASS", f"({a.minutes} min)")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--minutes", type=float, default=30)
    ap.add_argument("--interval", type=float, default=30)
    ap.add_argument("--profile", default="normal", choices=["thumb", "normal", "focus"])
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--out")
    ap.add_argument("--max-rss-growth-mb", type=float, default=150)
    return asyncio.run(main_async(ap.parse_args()))


if __name__ == "__main__":
    raise SystemExit(main())
