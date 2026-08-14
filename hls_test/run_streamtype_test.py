#!/usr/bin/env python3
"""Ear-timing run: same MP3 URL, three stream_type values, back to back.

Every test in this project so far has used stream_type='LIVE'. That flag tells
the receiver the stream has no end and no seekable range, which is exactly the
condition that would justify a large safety buffer - so it is a plausible
cause of the ~20-26s wait rather than an innocent bystander.

Identical URL and identical audio across all three legs; the only variable is
the flag. The source beeps once per second, so the first beep marks true
playback start within 1s.

player_state is printed but is a proven liar on this hardware (it reported
PLAYING at +4.6s when audio actually began at +24s). Ears are the measurement.

Volume is left as found and restored in a finally block.
"""
import time

import pychromecast

TARGET = "Living Room speaker"
URL = "http://192.168.7.1:8000/beeptest.mp3"
WINDOW = 35
GAP = 8
LEGS = ["BUFFERED", "NONE", "LIVE"]

casts, browser = pychromecast.get_chromecasts(tries=5, timeout=5)
cc = next(c for c in casts if c.device.friendly_name == TARGET)
cc.wait()
original = cc.status.volume_level
print(f"target={TARGET}  volume={original:.3f} (unchanged)")
print(f"url={URL}\n")

results = []
try:
    for st_type in LEGS:
        if cc.app_id:
            cc.quit_app()
            time.sleep(1.5)
            cc.wait()

        print("=" * 58)
        print(f"LEG: stream_type={st_type}")
        print(f"START {time.strftime('%H:%M:%S')}  <-- first beep = playback start")
        print("=" * 58, flush=True)

        t0 = time.monotonic()
        cc.media_controller.play_media(URL, "audio/mp3", stream_type=st_type)

        seen = {}
        last_tick = 0
        while True:
            el = time.monotonic() - t0
            if el >= WINDOW:
                break
            s = cc.media_controller.status.player_state
            if s and s not in seen:
                seen[s] = el
                print(f"  [state] {s:<12} +{el*1000:.0f}ms", flush=True)
            if int(el) >= last_tick + 5:
                last_tick = int(el) // 5 * 5
                print(f"  ...{last_tick:>3}s", flush=True)
            time.sleep(0.05)

        results.append((st_type, seen))
        print(f"  final={cc.media_controller.status.player_state}\n", flush=True)
        cc.quit_app()
        time.sleep(GAP)

    print("\n" + "=" * 58)
    print("SUMMARY  (states are unreliable - record what you HEARD)")
    for st_type, seen in results:
        states = ", ".join(f"{k}@{v:.1f}s" for k, v in seen.items())
        print(f"  stream_type={st_type:<9} {states}")
    print("=" * 58)
finally:
    try:
        cc.quit_app()
    except Exception:
        pass
    time.sleep(0.5)
    cc.set_volume(original)
    browser.stop_discovery()
