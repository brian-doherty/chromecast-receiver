# Doherty Cast Receiver

A custom Cast Application Framework (CAF) web receiver for the multi-room
ALSA-to-Chromecast bridge on `mediaserver.dohertyfamily.me`.

It exists for one reason: the stock Default Media Receiver (`CC1AD845`) waits
for roughly 20-26 seconds of buffered audio before starting playback of a
freshly-started live stream. That policy lives inside the receiver app running
on the Chromecast, so it is invisible to and uncontrollable from the sender
(`pychromecast`). Owning the receiver is the only way to change it. See
`CONTEXT.md` for the full investigation and everything already ruled out.

## Two playback modes

| Mode | What it does | Why |
|---|---|---|
| `caf` (default) | CAF's own player, with `playbackConfig` buffering turned as low as the SDK allows | Cheapest thing that might work |
| `direct` | Bypasses CAF's media pipeline entirely, drives a raw `<audio>` element | Several `playbackConfig` buffering fields are only honoured by the adaptive (Shaka) pipeline. A progressive Icecast MP3 goes through the media element instead, so `caf` mode may not move the number at all. |

Select a mode per-request via `customData.mode`, per-app via `?mode=direct` in
the URL registered in the console, or at runtime with a `SET_MODE` message on
`urn:x-cast:me.dohertyfamily.cast`.

## Registering in the Cast Developer Console

1. https://cast.google.com/publish → **Add New Application** → **Custom Receiver**.
2. **Application URL**: the GitHub Pages URL of `index.html`.
3. **Check "Supports casting to audio-only devices."** Chromecast Audio devices
   will not discover or launch the app without this. Easiest way to lose an
   afternoon.
4. Guest mode is not needed.
5. Save, and note the **Application ID**.

Then:

- Register each of the 3 physical Chromecast Audio serial numbers under
  **Cast Receiver Devices**. Cast Groups have no serial number and can't be
  registered, but `insidehome` and `wholehome` are made up entirely of those
  3 devices, so both are covered.
- **Reboot each device** after registering it. They only pick up debug-device
  status on boot.
- Allow ~15 minutes for a new or edited app registration to propagate before
  concluding anything is broken.

The app stays **unpublished**. Registered test devices launch unpublished
receivers indefinitely; no review or publication is needed for personal use.

## Testing

```bash
export CAST_APP_ID=<application id from the console>

# stock receiver baseline
PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python ./cast_latency_test.py familyroom --app stock

# custom receiver, CAF pipeline
PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python ./cast_latency_test.py familyroom

# custom receiver, raw <audio>
PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python ./cast_latency_test.py familyroom --mode direct
```

The receiver reports its own timing marks back over the custom namespace, so
the script prints both sender-side state transitions and receiver-side
milestones. **Still ear-time the result** — `player_state` was already proven
unreliable as a proxy for actual audible output on this hardware. The script
prints a wall-clock `START` line to time against.

For an end-to-end test through the real audio path, use the established
procedure: force-quit the app, confirm `app_id` is `None`, then

```bash
ffmpeg -f lavfi -i "sine=frequency=440:duration=30" -ar 44100 -ac 2 test_tone.wav
aplay -D chromecast_familyroom test_tone.wav
```

and listen for the actual audible start. (`aplay` cannot decode MP3 — it will
play the raw bytes as noise. Use WAV.)

## Live debugging on the device

Registered debug devices expose a remote debugger. With the receiver running:

```
chrome://inspect  →  Configure...  →  add <device-ip>:9222
```

The receiver's `console.log` output and the Cast Debug Logger both surface
there.

## Wiring it into production

`cast_arbitrator.py`'s `start_cast()` needs one line. `MediaController`
launches whatever is in `self.app_id`, defaulting to the stock receiver:

```python
mc = cast.media_controller
mc.app_id = CUSTOM_APP_ID          # <-- add this
mc.play_media(url, "audio/mp3", stream_type="LIVE")
```

To pin a mode from the arbitrator, pass it through `media_info`:

```python
mc.play_media(url, "audio/mp3", stream_type="LIVE",
              media_info={"customData": {"mode": "direct"}})
```

Don't do this until the latency numbers actually justify it.

## Deploying changes

GitHub Pages serves from `main`. Push, wait for the Pages build, then
force-quit the app on the device so it reloads the page:

```bash
git push
# receiver pages are cached; force-quit picks up the new version
```
