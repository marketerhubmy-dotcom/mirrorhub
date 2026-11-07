"""Streaming pipeline tests using synthetic H.264 byte streams (no phone needed).

These prove splitter/hub/session plumbing only. They are NOT evidence that a
real phone streams through the bundled scrcpy 4.0 server (see QA_MATRIX #6).
"""
import asyncio

import pytest

from app.services import scrcpy_stream as ss
from app.services.scrcpy_stream import START4, AnnexBSplitter, StreamHub, StreamSession

SPS = START4 + b"\x67\x42\xc0\x1e\xaa\xbb"
PPS = START4 + b"\x68\xce\x3c\x80"
IDR = START4 + b"\x65\x88\x84\x00\x10"
P1 = START4 + b"\x41\x9a\x01\x02"
P2 = START4 + b"\x41\x9a\x03\x04"


def stream(*nals, three_byte=False):
    data = b"".join(nals)
    return data.replace(START4, b"\x00\x00\x01") if three_byte else data


# ── splitter ──────────────────────────────────────────────────────────────────

def test_splitter_emits_all_but_last_then_flush():
    sp = AnnexBSplitter()
    out = sp.feed(stream(SPS, PPS, IDR))
    assert out == [SPS, PPS]            # IDR still pending (next start code unseen)
    assert sp.flush() == [IDR]
    assert sp.flush() == []


def test_splitter_handles_arbitrary_chunking():
    data = stream(SPS, PPS, IDR, P1, P2)
    for size in (1, 2, 3, 5, 7, 4096):
        sp, got = AnnexBSplitter(), []
        for i in range(0, len(data), size):
            got += sp.feed(data[i:i + size])
        got += sp.flush()
        assert got == [SPS, PPS, IDR, P1, P2], f"chunk size {size}"


def test_splitter_normalises_three_byte_start_codes():
    sp = AnnexBSplitter()
    got = sp.feed(stream(SPS, PPS, IDR, three_byte=True)) + sp.flush()
    assert got == [SPS, PPS, IDR]


def test_splitter_discards_leading_garbage_and_survives_no_start_code():
    sp = AnnexBSplitter()
    assert sp.feed(b"\x11\x22\x33\x44\x55") == []
    assert sp.feed(stream(SPS, PPS)) == [SPS]
    assert sp.flush() == [PPS]


# ── hub ───────────────────────────────────────────────────────────────────────

def drain(v):
    out = []
    while not v.queue.empty():
        out.append(v.queue.get_nowait())
    return out


def test_late_joiner_gets_config_and_current_gop():
    hub = StreamHub()
    for n in (SPS, PPS, IDR, P1):
        hub.push(n)
    v = hub.subscribe()
    assert drain(v) == [SPS, PPS, IDR, P1]
    hub.push(P2)
    assert drain(v) == [P2]


def test_new_idr_resets_gop_cache():
    hub = StreamHub()
    for n in (SPS, PPS, IDR, P1, IDR, P2):
        hub.push(n)
    assert drain(hub.subscribe()) == [SPS, PPS, IDR, P2]


def test_no_priming_before_first_keyframe():
    hub = StreamHub()
    hub.push(SPS); hub.push(PPS); hub.push(P1)
    assert drain(hub.subscribe()) == []


def test_slow_viewer_drops_until_next_keyframe_without_affecting_fast_viewer():
    hub = StreamHub(viewer_queue=4)
    for n in (SPS, PPS, IDR):
        hub.push(n)
    fast, slow = hub.subscribe(), hub.subscribe()
    drain(fast); drain(slow)
    for i in range(10):
        hub.push(P1)
        drain(fast)                      # fast keeps up
    assert slow.waiting_key and slow.dropped > 0
    drain(slow)
    hub.push(P2)                          # still waiting: P-frames are discarded
    assert drain(slow) == []
    hub.push(IDR)
    got = drain(slow)
    assert got[-1] == IDR and not slow.waiting_key
    assert len(got) >= 1


def test_hubs_are_isolated_per_device():
    a, b = StreamHub(), StreamHub()
    va, vb = a.subscribe(), b.subscribe()
    a.push(SPS); a.push(PPS); a.push(IDR)
    assert len(drain(va)) == 3 and drain(vb) == []


# ── server command / adb helpers ──────────────────────────────────────────────

def test_server_args_use_options_present_in_bundled_4_0_server():
    args = ss.build_server_args("4.0", "0abc1234", "thumb")
    assert args[0] == "4.0"
    for must in ("raw_stream=true", "tunnel_forward=true", "control=false", "audio=false",
                 "scid=0abc1234", "video_codec=h264", "max_size=480"):
        assert must in args
    assert not any("codec_meta" in a for a in args)  # removed in 4.0


def test_profiles_scale_quality():
    assert ss.PROFILES["thumb"]["max_fps"] < ss.PROFILES["focus"]["max_fps"]
    assert ss.PROFILES["thumb"]["video_bit_rate"] < ss.PROFILES["focus"]["video_bit_rate"]


@pytest.mark.parametrize("out,port", [("12345\n", 12345), ("* daemon started\n54321", 54321)])
def test_parse_forward_port(out, port):
    assert ss.parse_forward_port(out) == port


def test_parse_forward_port_rejects_garbage():
    with pytest.raises(RuntimeError):
        ss.parse_forward_port("error: closed")


def test_manager_rejects_unknown_profile():
    with pytest.raises(ValueError):
        ss.StreamManager().attach("d", "1.2.3.4:5555", "ultra")


# ── session pump over a real localhost socket ─────────────────────────────────

async def _serve(chunks, delay=0.0):
    async def handle(_r, w):
        for c in chunks:
            w.write(c)
            await w.drain()
            if delay:
                await asyncio.sleep(delay)
        await asyncio.sleep(0.25)  # silence (> IDLE_FLUSH_S) before EOF
        w.close()
    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    return server, server.sockets[0].getsockname()[1]


@pytest.mark.asyncio
async def test_pump_delivers_nals_and_flushes_static_screen():
    # Last P-frame is followed by silence (static screen): must still be delivered.
    data = stream(SPS, PPS, IDR, P1)
    server, port = await _serve([data[:7], data[7:]], delay=0.01)
    async with server:
        sess = StreamSession("dev-A", "1.2.3.4:5555", "thumb")
        viewer = sess.hub.subscribe()
        reader, _w = await asyncio.open_connection("127.0.0.1", port)
        with pytest.raises(ConnectionError):
            await sess._pump(reader)
    assert drain(viewer) == [SPS, PPS, IDR, P1]
    assert sess.hub.frames == 2


@pytest.mark.asyncio
async def test_two_sessions_two_devices_do_not_mix_streams():
    a_nals = stream(SPS, PPS, IDR, P1)
    b_nals = stream(SPS, PPS, IDR, P2)
    sa, pa = await _serve([a_nals])
    sb, pb = await _serve([b_nals])
    async with sa, sb:
        A = StreamSession("dev-A", "10.0.0.1:5555", "thumb")
        B = StreamSession("dev-B", "10.0.0.2:5555", "thumb")
        va, vb = A.hub.subscribe(), B.hub.subscribe()
        ra, _ = await asyncio.open_connection("127.0.0.1", pa)
        rb, _ = await asyncio.open_connection("127.0.0.1", pb)
        for sess, r in ((A, ra), (B, rb)):
            with pytest.raises(ConnectionError):
                await sess._pump(r)
    got_a, got_b = drain(va), drain(vb)
    assert P1 in got_a and P2 not in got_a
    assert P2 in got_b and P1 not in got_b
