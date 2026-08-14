#!/bin/bash
# Drop the pre-cast encoder restart from cast_arbitrator.py.
#
# restart_encoder() existed only to work around the stock receiver's ~20s
# buffering: a freshly-started mount had no stale silence in its burst window.
# With the custom receiver in direct mode that mitigation may be dead weight -
# it costs a systemctl restart plus a 2s settle on every activation.
#
# Counterpoint worth measuring rather than assuming: a long-running mount does
# have a burst window, so Icecast will hand the receiver ~2.7s of stale silence
# (64KB at 192kbps) on connect, which the audio element plays through in real
# time. This change may therefore be a wash. Measure, don't guess.
#
# The function itself is left defined and simply not called, so reverting is a
# one-line change either way.
#
# Run as root:  sudo bash patch_remove_encoder_restart.sh
# Revert:       sudo bash patch_remove_encoder_restart.sh --revert

set -euo pipefail

FILE=/usr/local/bin/cast_arbitrator.py
BACKUP="${FILE}.bak-preencoderrestart"

MARK="# restart_encoder disabled:"

if [ "${1:-}" = "--revert" ]; then
  if [ ! -f "$BACKUP" ]; then
    echo "No backup at $BACKUP - nothing to revert." >&2
    exit 1
  fi
  cp -a "$BACKUP" "$FILE"
  systemctl restart cast-arbitrator.service
  echo "Restored the encoder restart and restarted cast-arbitrator."
  exit 0
fi

if grep -q "$MARK" "$FILE"; then
  echo "Already patched."
  exit 0
fi

[ -f "$BACKUP" ] || cp -a "$FILE" "$BACKUP"
echo "Backup at $BACKUP"

python3 - "$FILE" <<'PY'
import sys

path = sys.argv[1]
src = open(path).read()

old = """        # Fresh encoder so the mount's buffer is real audio, not stale
        # silence - see module docstring for why this matters.
        restart_encoder(zone)
        time.sleep(ENCODER_RESTART_SETTLE_SECS)
"""

new = """        # restart_encoder disabled: it existed only to deny the stock
        # receiver a stale-silence burst window. The custom receiver in
        # direct mode starts in ~6s regardless, so the restart plus its 2s
        # settle is pure cost. Re-enable with
        # patch_remove_encoder_restart.sh --revert if latency regresses.
        # restart_encoder(zone)
        # time.sleep(ENCODER_RESTART_SETTLE_SECS)
"""

if old not in src:
    sys.exit("Could not find the restart_encoder call block; aborting.")

open(path, 'w').write(src.replace(old, new, 1))
print("Disabled restart_encoder() in activate_zone().")
PY

python3 -m py_compile "$FILE"
echo "Syntax OK."

systemctl restart cast-arbitrator.service
sleep 2
systemctl is-active --quiet cast-arbitrator.service \
  && echo "cast-arbitrator restarted and active." \
  || { echo "cast-arbitrator FAILED to start - reverting."; cp -a "$BACKUP" "$FILE"; \
       systemctl restart cast-arbitrator.service; exit 1; }
