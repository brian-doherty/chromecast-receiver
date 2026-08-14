#!/usr/bin/env python3
"""Eviction test for direct mode.

Chromecast allows one session per physical speaker, so when a group starts,
cast_arbitrator.py must evict any solo zone sharing a speaker with it. It
does that with media_controller.stop() - which in direct mode does not reach
the <audio> element unless the receiver intercepts STOP. This verifies that
interception works on real hardware.

Sequence:
  t=0   440 Hz -> chromecast_livingroom   (Living Room solo should start)
  t=18  880 Hz -> chromecast_insidehome   (group takes Family Room + Living
                                           Room; the 440 Hz must stop)

What you should hear on Living Room: a low tone, then it switches to the
higher tone. If you hear both at once, or the low tone keeps going, eviction
failed and the patch should be reverted.
"""
import subprocess
import time

import pychromecast

DIR = "/home/brian/projects/chromecast-receiver"
WATCH = ["Living Room speaker", "Family Room speaker", "Inside Home Group"]
SOLO_AT, GROUP_AT, END_AT = 0, 18, 40

casts, browser = pychromecast.get_chromecasts(tries=6, timeout=6)
devs = {}
for name in WATCH:
    cc = next((c for c in casts if c.device.friendly_name == name), None)
    if cc:
        cc.wait()
        devs[name] = cc

procs = []
t0 = time.monotonic()


def el():
    return time.monotonic() - t0


def snapshot(tag):
    print(f"\n--- {tag}  (t={el():.1f}s) ---", flush=True)
    for name, cc in devs.items():
        try:
            st = cc.media_controller.status
            content = (st.content_id or "")[-20:] if st.content_id else None
            print(f"  {name:22} app={str(cc.app_id):10} state={str(st.player_state):10} {content}",
                  flush=True)
        except Exception as exc:
            print(f"  {name:22} <error {exc}>", flush=True)


def play(pcm, wav):
    p = subprocess.Popen(["aplay", "-D", pcm, f"{DIR}/{wav}"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    procs.append(p)
    print(f"[t={el():.1f}s] aplay {wav} -> {pcm}", flush=True)


try:
    snapshot("before anything")

    print(f"\n=== t=0: LIVING ROOM SOLO, 440 Hz (low tone) ===", flush=True)
    play("chromecast_livingroom", "tone440.wav")

    while el() < GROUP_AT:
        time.sleep(0.5)
    snapshot("solo established")

    print(f"\n=== t={GROUP_AT}: INSIDE HOME GROUP, 880 Hz (high tone) ===")
    print("    Living Room must switch to the high tone, not play both.", flush=True)
    play("chromecast_insidehome", "tone880.wav")

    for mark in (GROUP_AT + 8, GROUP_AT + 16):
        while el() < mark:
            time.sleep(0.5)
        snapshot(f"after group start (+{mark - GROUP_AT}s)")

    while el() < END_AT:
        time.sleep(0.5)
finally:
    for p in procs:
        p.terminate()
    time.sleep(1)
    for p in procs:
        try:
            p.wait(timeout=3)
        except Exception:
            p.kill()
    print("\naplay stopped. Letting the arbitrator settle...", flush=True)
    time.sleep(6)
    snapshot("after everything stopped")
    browser.stop_discovery()
