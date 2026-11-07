# Simulated-phone harness (NOT hardware evidence)

Runs the real `video_endpoint`, `control_endpoint`, `StreamHub`, `AccessUnitAssembler`
and `LoopbackGuardMiddleware`; only ADB and the DB are faked. Used to verify the
browser decode path (WebCodecs) and click→device routing without a phone.

```
pip install av numpy            # in a scratch venv, not the project venv
python gen_h264.py single.h264 single   # one slice per picture (typical phone encoder)
python gen_h264.py multi.h264 multi     # many slices per picture (regression case)
python fake_phone_server.py <backend_dir> <frontend/dist> single.h264 8791
# open http://127.0.0.1:8791/device-wall  (use a fresh query string to defeat Chrome's cache)
# GET /__log shows the shell commands that would have been typed into each fake device.
```
