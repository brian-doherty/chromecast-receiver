#!/usr/bin/env python3
"""Ear-timing run: raise volume 3x, cast the packed-AAC HLS leg, restore volume.

The source beeps once per second, so the first beep lands within 1s of true
playback start. Volume is restored in a finally block so an exception or
Ctrl-C cannot leave the speaker loud.
"""
import sys
import time

import pychromecast

URL = "http://192.168.7.1:8099/aac/stream.m3u8"
CTYPE = "application/x-mpegurl"
TARGET = "Family Room speaker"
WINDOW = 60

casts, browser = pychromecast.get_chromecasts(tries=5, timeout=5)
cc = next(c for c in casts if c.device.friendly_name == TARGET)
cc.wait()

# Volume is already at the level the user wants (0.322, matching Living Room),
# so leave it alone. Kept as a multiplier rather than deleted so the restore
# path below stays exercised.
original = cc.status.volume_level
target_vol = original

try:
    if cc.app_id:
        cc.quit_app()
        time.sleep(1.5)
        cc.wait()

    cc.set_volume(target_vol)
    time.sleep(1.0)
    print(f"volume {original:.3f} -> {cc.status.volume_level:.3f}")

    mc = cc.media_controller
    print(f"\nurl={URL}  target={TARGET}")
    print(f"START {time.strftime('%H:%M:%S')}  <-- first beep = playback start\n", flush=True)
    t0 = time.monotonic()
    mc.play_media(URL, CTYPE, stream_type="LIVE")

    seen = {}
    while time.monotonic() - t0 < WINDOW:
        st = mc.status.player_state
        el = time.monotonic() - t0
        if st and st not in seen:
            seen[st] = el * 1000
            print(f"  {st:<12} +{seen[st]:.0f}ms", flush=True)
        # Periodic wall-clock ticks give the listener something to count against.
        if abs(el - round(el)) < 0.03 and round(el) % 5 == 0 and round(el) > 0:
            print(f"  ...{round(el):>3}s elapsed", flush=True)
            time.sleep(0.1)
        time.sleep(0.03)

    print(f"\nfinal player_state={mc.status.player_state} idle_reason={mc.status.idle_reason}")
finally:
    try:
        cc.quit_app()
    except Exception:
        pass
    time.sleep(0.5)
    cc.set_volume(original)
    time.sleep(0.8)
    print(f"volume restored -> {cc.status.volume_level:.3f}")
    browser.stop_discovery()
