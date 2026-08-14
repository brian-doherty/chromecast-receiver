#!/bin/bash
# Point cast_arbitrator.py at the custom receiver.
#
# MediaController.play_media() launches whatever is in self.app_id, which
# defaults to the stock Default Media Receiver (CC1AD845). Setting it to our
# app is the entire sender-side change - the receiver defaults to 'direct'
# mode on its own, so no customData plumbing is needed here.
#
# Measured 21s -> 6s ear-timed on Living Room speaker.
#
# Run as root:  sudo bash patch_arbitrator.sh
# Revert:       sudo bash patch_arbitrator.sh --revert

set -euo pipefail

FILE=/usr/local/bin/cast_arbitrator.py
BACKUP="${FILE}.bak-precustomreceiver"
APP_ID="95C13CF9"

if [ "${1:-}" = "--revert" ]; then
  if [ ! -f "$BACKUP" ]; then
    echo "No backup at $BACKUP - nothing to revert." >&2
    exit 1
  fi
  cp -a "$BACKUP" "$FILE"
  systemctl restart cast-arbitrator.service
  echo "Reverted to stock receiver and restarted cast-arbitrator."
  exit 0
fi

if grep -q "media_controller.app_id" "$FILE"; then
  echo "Already patched - $FILE references media_controller.app_id."
  exit 0
fi

[ -f "$BACKUP" ] || cp -a "$FILE" "$BACKUP"
echo "Backup at $BACKUP"

python3 - "$FILE" "$APP_ID" <<'PY'
import sys

path, app_id = sys.argv[1], sys.argv[2]
src = open(path).read()

old = '            cc.media_controller.play_media(url, "audio/mp3", stream_type="LIVE")'
new = (
    '            # Custom CAF receiver. play_media() launches whatever is in\n'
    '            # app_id; the default is the stock receiver, whose ~20s\n'
    '            # buffering policy is what this whole change exists to avoid.\n'
    '            # The receiver defaults to direct mode on its own.\n'
    f'            cc.media_controller.app_id = "{app_id}"\n'
    '            cc.media_controller.play_media(url, "audio/mp3", stream_type="LIVE")'
)

if old not in src:
    sys.exit(f"Could not find the play_media call to patch in {path}; aborting.")

open(path, 'w').write(src.replace(old, new, 1))
print("Patched start_cast().")
PY

python3 -m py_compile "$FILE"
echo "Syntax OK."

systemctl restart cast-arbitrator.service
sleep 2
systemctl is-active --quiet cast-arbitrator.service \
  && echo "cast-arbitrator restarted and active." \
  || { echo "cast-arbitrator FAILED to start - reverting."; cp -a "$BACKUP" "$FILE"; \
       systemctl restart cast-arbitrator.service; exit 1; }
