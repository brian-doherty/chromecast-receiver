#!/usr/bin/env python3
"""Back-to-back ear-timing run: packed-ADTS HLS, then progressive MP3 baseline.

One quiet window covers both legs. Each leg announces a START line, counts
elapsed seconds aloud in the log, and reports how many segments the device
actually fetched (HLS leg) so server-side evidence lines up with what was
heard.

The source beeps once per second, so the first beep lands within 1s of true
playback start. player_state is printed but is known-unreliable on this
hardware - the ears are the measurement.

Volume is left exactly as found, and restored in a finally block so an
interrupt cannot leave a speaker changed.
"""
import subprocess
import time

import pychromecast

TARGET = "Family Room speaker"
WINDOW = 40
GAP = 8
LOG = "/home/brian/projects/chromecast-receiver/hls_test/http.log"

LEGS = [
    ("HLS  (packed ADTS)", "http://192.168.7.1:8099/aac/stream.m3u8",
     "application/x-mpegurl"),
    ("MP3  (baseline)", "http://192.168.7.1:8000/beeptest.mp3", "audio/mp3"),
]


def seg_count():
    try:
        out = subprocess.run(["grep", "-c", r"\.aac", LOG],
                             capture_output=True, text=True).stdout.strip()
        return int(out or 0)
    except Exception:
        return 0


casts, browser = pychromecast.get_chromecasts(tries=5, timeout=5)
cc = next(c for c in casts if c.device.friendly_name == TARGET)
cc.wait()
original = cc.status.volume_level
print(f"target={TARGET}  volume={original:.3f} (unchanged)\n")

results = []
try:
    for name, url, ctype in LEGS:
        if cc.app_id:
            cc.quit_app()
            time.sleep(1.5)
            cc.wait()

        before = seg_count()
        print("=" * 58)
        print(f"LEG: {name}")
        print(f"     {url}")
        print(f"START {time.strftime('%H:%M:%S')}  <-- first beep = playback start")
        print("=" * 58, flush=True)

        t0 = time.monotonic()
        cc.media_controller.play_media(url, ctype, stream_type="LIVE")

        seen = {}
        last_tick = 0
        while True:
            el = time.monotonic() - t0
            if el >= WINDOW:
                break
            st = cc.media_controller.status.player_state
            if st and st not in seen:
                seen[st] = el
                print(f"  [state] {st:<12} +{el*1000:.0f}ms", flush=True)
            if int(el) >= last_tick + 5:
                last_tick = int(el) // 5 * 5
                print(f"  ...{last_tick:>3}s", flush=True)
            time.sleep(0.05)

        fetched = seg_count() - before
        results.append((name, seen, fetched))
        print(f"  segments fetched by device: {fetched}")
        print(f"  final state={cc.media_controller.status.player_state} "
              f"idle_reason={cc.media_controller.status.idle_reason}\n", flush=True)

        cc.quit_app()
        time.sleep(GAP)

    print("\n" + "=" * 58)
    print("SUMMARY")
    for name, seen, fetched in results:
        states = ", ".join(f"{k}@{v:.1f}s" for k, v in seen.items())
        print(f"  {name:22} segs={fetched:<4} states: {states}")
    print("=" * 58)
finally:
    try:
        cc.quit_app()
    except Exception:
        pass
    time.sleep(0.5)
    cc.set_volume(original)
    browser.stop_discovery()
