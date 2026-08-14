#!/usr/bin/env python3
"""Cast an arbitrary URL to a zone and log sender-side state transitions.

player_state is a known-unreliable proxy for audible output on this hardware,
so this prints a wall-clock START line to ear-time the first beep against.
The source beeps once per second, so the first beep lands within 1s of true
playback start.
"""
import sys
import time

import pychromecast

URLS = {
    "hls": ("http://192.168.7.1:8099/stream.m3u8", "application/x-mpegurl"),
    "mp3": ("http://192.168.7.1:8000/beeptest.mp3", "audio/mp3"),
    "aac": ("http://192.168.7.1:8099/aac/stream.m3u8", "application/x-mpegurl"),
}

which = sys.argv[1]
target = sys.argv[2] if len(sys.argv) > 2 else "Family Room speaker"
url, ctype = URLS[which]

casts, browser = pychromecast.get_chromecasts(tries=5, timeout=5)
cc = next(c for c in casts if c.device.friendly_name == target)
cc.wait()
if cc.app_id:
    cc.quit_app()
    time.sleep(1.5)
    cc.wait()

mc = cc.media_controller
print(f"\nleg={which}  url={url}  target={target}  volume={cc.status.volume_level:.2f}")
print(f"START {time.strftime('%H:%M:%S.')}{int(time.time()%1*1000):03d}  <-- listen for the first beep\n", flush=True)
t0 = time.monotonic()
mc.play_media(url, ctype, stream_type="LIVE")

seen = {}
while time.monotonic() - t0 < 45:
    st = mc.status.player_state
    if st and st not in seen:
        seen[st] = (time.monotonic() - t0) * 1000
        print(f"  {st:<12} +{seen[st]:.0f}ms", flush=True)
    time.sleep(0.05)

print(f"\nidle_reason={mc.status.idle_reason} content={mc.status.content_id}")
cc.quit_app()
browser.stop_discovery()
