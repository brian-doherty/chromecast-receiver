#!/usr/bin/env python3
"""The payoff test: custom receiver vs the stock-receiver baseline.

Same beep source and same URL as every earlier measurement, so the numbers
are directly comparable to the established baseline (21-24s ear-timed).

Three legs:
  1. custom receiver, 'caf' mode    - CAF player with playbackConfig tuned down
  2. custom receiver, 'direct' mode - bypasses CAF, raw <audio> element
  3. stock receiver                 - in-session control

Mode is passed per-request as customData, which the receiver's LOAD
interceptor reads. The receiver also reports timing marks back over
urn:x-cast:me.dohertyfamily.cast, so receiver-side milestones print
alongside what you hear.

Volume left as found, restored in a finally block.
"""
import time

import pychromecast
from pychromecast.controllers import BaseController

NS = "urn:x-cast:me.dohertyfamily.cast"
CUSTOM_APP_ID = "95C13CF9"
STOCK_APP_ID = "CC1AD845"
URL = "http://192.168.7.1:8000/beeptest.mp3"
TARGET = "Living Room speaker"
WINDOW = 35
GAP = 8


class TimingController(BaseController):
    def __init__(self):
        super().__init__(NS)
        self.marks = []

    def receive_message(self, _message, data: dict):
        t = data.get("type")
        if t == "MARK":
            self.marks.append((data["label"], data["ms"]))
            print(f"  [recv]  {data['label']:<22} +{data['ms']}ms", flush=True)
        elif t == "LOAD":
            print(f"  [recv]  LOAD mode={data.get('mode')}", flush=True)
        elif t == "ERROR":
            print(f"  [recv]  ERROR {data.get('detail')}", flush=True)
        return True


# 'direct' first: it is the leg that matters and deserves fresh attention.
# Stock last as an in-session control against rig drift.
LEGS = [
    ("custom / direct", CUSTOM_APP_ID, {"customData": {"mode": "direct"}}),
    ("custom / caf", CUSTOM_APP_ID, {"customData": {"mode": "caf"}}),
    ("stock baseline", STOCK_APP_ID, None),
]

casts, browser = pychromecast.get_chromecasts(tries=6, timeout=6)
cc = next(c for c in casts if c.device.friendly_name == TARGET)
cc.wait()
timing = TimingController()
cc.register_handler(timing)

original = cc.status.volume_level
print(f"target={TARGET}  volume={original:.3f} (unchanged)")
print(f"url={URL}\nbaseline to beat: 21-24s ear-timed\n")

try:
    for name, app_id, media_info in LEGS:
        if cc.app_id:
            cc.quit_app()
            time.sleep(1.5)
            cc.wait()
        timing.marks = []

        print("=" * 58)
        print(f"LEG: {name}   (app {app_id})")
        print(f"START {time.strftime('%H:%M:%S')}  <-- first beep = playback start")
        print("=" * 58, flush=True)

        mc = cc.media_controller
        mc.app_id = app_id
        t0 = time.monotonic()
        mc.play_media(URL, "audio/mp3", stream_type="LIVE", media_info=media_info)

        seen, last_tick = {}, 0
        while True:
            el = time.monotonic() - t0
            if el >= WINDOW:
                break
            s = mc.status.player_state
            if s and s not in seen:
                seen[s] = el
                print(f"  [state] {s:<12} +{el*1000:.0f}ms", flush=True)
            if int(el) >= last_tick + 5:
                last_tick = int(el) // 5 * 5
                print(f"  ...{last_tick:>3}s", flush=True)
            time.sleep(0.05)

        print("", flush=True)
        cc.quit_app()
        time.sleep(GAP)
finally:
    try:
        cc.quit_app()
    except Exception:
        pass
    time.sleep(0.5)
    cc.set_volume(original)
    browser.stop_discovery()
