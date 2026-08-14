#!/usr/bin/env python3
"""Measure time-to-audible for a zone, against either receiver app.

Compares the stock Default Media Receiver baseline against our custom
receiver. The custom receiver reports its own internal timing marks back
over a custom namespace, so the numbers here cover both sides of the link.

Run with the protobuf workaround (see CONTEXT.md):

    PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python ./cast_latency_test.py familyroom
    PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python ./cast_latency_test.py familyroom --app stock
    PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python ./cast_latency_test.py familyroom --mode direct

The receiver's marks tell you when *it* thinks playback started. That was
already shown to be an unreliable proxy for actual audible output on this
hardware, so still ear-time the result: the script prints a wall-clock
"START" line to time against.
"""

import argparse
import json
import os
import sys
import time

import pychromecast
from pychromecast.controllers import BaseController

NAMESPACE = "urn:x-cast:me.dohertyfamily.cast"
STOCK_APP_ID = "CC1AD845"

# Registered in the Cast Developer Console as an unpublished Custom Receiver.
CUSTOM_APP_ID = os.environ.get("CAST_APP_ID", "95C13CF9")

ZONES = {
    "backyard": "Backyard speaker",
    "familyroom": "Family Room speaker",
    "livingroom": "Living Room speaker",
    "insidehome": "Inside Home Group",
    "wholehome": "Whole Home Group",
}

STREAM_URL = "http://192.168.7.1:8000/{zone}.mp3"


class TimingController(BaseController):
    """Receives the timing marks our custom receiver reports."""

    def __init__(self):
        super().__init__(NAMESPACE)
        self.marks = []

    def receive_message(self, _message, data: dict):
        if data.get("type") == "MARK":
            self.marks.append((data["label"], data["ms"]))
            print(f"    receiver: {data['label']:<24} +{data['ms']}ms")
        elif data.get("type") == "ERROR":
            print(f"    receiver ERROR: {data.get('detail')}", file=sys.stderr)
        elif data.get("type") == "LOAD":
            print(f"    receiver: LOAD {data.get('contentId')}")
        return True


def find_cast(friendly_name):
    casts, browser = pychromecast.get_chromecasts(tries=5, timeout=5)
    cast = next(
        (cc for cc in casts if cc.device.friendly_name == friendly_name), None
    )
    if cast is None:
        names = sorted(cc.device.friendly_name for cc in casts)
        browser.stop_discovery()
        sys.exit(f"Device {friendly_name!r} not found. Discovered: {names}")
    cast.wait()
    return cast, browser


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("zone", choices=sorted(ZONES))
    ap.add_argument(
        "--app",
        default="custom",
        choices=("custom", "stock"),
        help="which receiver app to launch (default: custom)",
    )
    ap.add_argument(
        "--mode",
        default=None,
        choices=("caf", "direct"),
        help="custom receiver playback mode; passed as customData",
    )
    ap.add_argument("--wait", type=float, default=40.0, help="seconds to observe")
    args = ap.parse_args()

    app_id = STOCK_APP_ID if args.app == "stock" else CUSTOM_APP_ID
    if not app_id:
        sys.exit(
            "No custom app id. Register the receiver in the Cast Developer "
            "Console, then set CAST_APP_ID=<id> (or edit CUSTOM_APP_ID)."
        )

    url = STREAM_URL.format(zone=args.zone)
    cast, browser = find_cast(ZONES[args.zone])

    timing = TimingController()
    if args.app == "custom":
        cast.register_handler(timing)

    # play_media() can silently no-op when the app is already running, because
    # its launch callback never fires. Always force-quit first.
    if cast.app_id:
        print(f"quitting running app {cast.app_id}")
        cast.quit_app()
        time.sleep(1.5)
        cast.wait()

    mc = cast.media_controller
    # MediaController.play_media() launches self.app_id; pointing it at our
    # receiver is the whole sender-side change (see cast_arbitrator.py).
    mc.app_id = app_id

    media_info = {}
    if args.mode:
        media_info["customData"] = {"mode": args.mode}

    print(f"\napp_id={app_id} zone={args.zone} url={url}")
    print(f"START {time.strftime('%H:%M:%S')} - listen for audio now\n")
    t0 = time.monotonic()

    mc.play_media(
        url,
        "audio/mp3",
        stream_type="LIVE",
        media_info=media_info or None,
    )

    seen = set()
    deadline = t0 + args.wait
    while time.monotonic() < deadline:
        state = mc.status.player_state
        if state and state not in seen:
            seen.add(state)
            print(f"    sender:   {state:<24} +{(time.monotonic() - t0) * 1000:.0f}ms")
        time.sleep(0.1)

    print("\n--- summary ---")
    print(f"sender states seen: {sorted(seen)}")
    if timing.marks:
        print("receiver marks:")
        for label, ms in timing.marks:
            print(f"  {label:<26} +{ms}ms")
    elif args.app == "custom":
        print("no receiver marks - receiver page never loaded or namespace mismatch")

    browser.stop_discovery()


if __name__ == "__main__":
    main()
