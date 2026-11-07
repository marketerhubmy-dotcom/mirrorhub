import av, numpy as np, sys
out = sys.argv[1]; SLICE_PARAMS = "sliced-threads=0:slices=1" if sys.argv[2] == "single" else "sliced-threads=1"
W, H, FPS, N = 540, 1200, 15, 150
c = av.open(out, "w", format="h264")
s = c.add_stream("libx264", rate=FPS)
s.width, s.height, s.pix_fmt = W, H, "yuv420p"
s.options = {"profile": "baseline", "g": "30", "bf": "0", "preset": "ultrafast", "tune": "zerolatency",
             "x264-params": SLICE_PARAMS + ":repeat-headers=1:annexb=1"}
for i in range(N):
    img = np.zeros((H, W, 3), np.uint8)
    img[:, :, 0] = np.linspace(20, 120, W, dtype=np.uint8)[None, :]
    img[:, :, 2] = np.linspace(20, 120, H, dtype=np.uint8)[:, None]
    img[0:120, 0:120] = (255, 0, 0)            # RED   top-left
    img[H-120:H, W-120:W] = (0, 0, 255)        # BLUE  bottom-right
    y = int((i / N) * (H - 100)); img[y:y+100, W//2-50:W//2+50] = (255, 255, 255)  # moving white box
    f = av.VideoFrame.from_ndarray(img, format="rgb24")
    for p in s.encode(f): c.mux(p)
for p in s.encode(): c.mux(p)
c.close()
