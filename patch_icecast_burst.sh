#!/bin/bash
# Disable Icecast's connect burst.
#
# burst-on-connect hands a new listener whatever is already sitting in the
# mount's buffer - which for an always-running encoder is stale silence. The
# custom receiver plays that through in real time before reaching live audio,
# so the burst is pure added latency for this workload. Icecast's own docs say
# to disable it for low-latency setups.
#
# Also collapses the two <burst-size> elements (65535 and 65536) into one.
# Icecast takes the last, so behaviour was never ambiguous, but the duplicate
# is cruft.
#
# Safety: backs up, edits only outside XML comments, validates well-formedness
# BEFORE touching the service, restarts icecast2, confirms it is listening,
# and restores the backup automatically if it is not. Then restarts the five
# encoders and waits for all five mounts to reappear.
#
# Expect all zones silent for roughly 5-15s. The encoders are Restart=always
# with RestartSec=5, so they self-heal even if this script is interrupted.
#
# Run as root:  sudo bash patch_icecast_burst.sh
# Revert:       sudo bash patch_icecast_burst.sh --revert

set -uo pipefail

CONF=/etc/icecast2/icecast.xml
BACKUP="${CONF}.bak-preburst"
ZONES=(backyard familyroom livingroom insidehome wholehome)

wait_for_icecast() {
  for _ in $(seq 1 20); do
    if curl -sf -m 3 -o /dev/null http://localhost:8000/status-json.xsl; then
      return 0
    fi
    sleep 1
  done
  return 1
}

mount_count() {
  curl -sf -m 5 http://localhost:8000/status-json.xsl 2>/dev/null | python3 -c "
import json,sys
try:
    d=json.load(sys.stdin)['icestats']
except Exception:
    print(0); sys.exit()
s=d.get('source',[])
s=[s] if isinstance(s,dict) else s
names={x.get('listenurl','').split('/')[-1] for x in s}
print(len([z for z in ['backyard.mp3','familyroom.mp3','livingroom.mp3','insidehome.mp3','wholehome.mp3'] if z in names]))
" 2>/dev/null || echo 0
}

restart_encoders() {
  for z in "${ZONES[@]}"; do
    systemctl restart "alsa-cast@${z}.service" || true
  done
}

if [ "${1:-}" = "--revert" ]; then
  if [ ! -f "$BACKUP" ]; then
    echo "No backup at $BACKUP - nothing to revert." >&2
    exit 1
  fi
  cp -a "$BACKUP" "$CONF"
  systemctl restart icecast2
  wait_for_icecast || { echo "icecast2 did not come back after revert!" >&2; exit 1; }
  restart_encoders
  echo "Reverted burst settings. Waiting for mounts..."
  for _ in $(seq 1 30); do
    [ "$(mount_count)" = "5" ] && { echo "All 5 mounts back."; exit 0; }
    sleep 2
  done
  echo "WARNING: not all 5 mounts returned - check 'systemctl status alsa-cast@*'." >&2
  exit 1
fi

[ -f "$BACKUP" ] || cp -a "$CONF" "$BACKUP"
echo "Backup at $BACKUP"

python3 - "$CONF" <<'PY'
import re
import sys

path = sys.argv[1]
src = open(path).read()

# Split into comment and non-comment spans so we never edit documentation.
parts = re.split(r'(<!--.*?-->)', src, flags=re.S)

changed = {'boc': 0, 'size': 0}
for i, part in enumerate(parts):
    if part.startswith('<!--'):
        continue
    part, n = re.subn(r'<burst-on-connect>\s*\d+\s*</burst-on-connect>',
                      '<burst-on-connect>0</burst-on-connect>', part)
    changed['boc'] += n
    part, n = re.subn(r'<burst-size>\s*\d+\s*</burst-size>',
                      '<burst-size>0</burst-size>', part)
    changed['size'] += n
    parts[i] = part

out = ''.join(parts)

# Collapse the duplicate burst-size elements now that both read 0.
dup = re.compile(r'([ \t]*<burst-size>0</burst-size>\n)(\s*<burst-size>0</burst-size>\n)')
while dup.search(out):
    out = dup.sub(r'\1', out, count=1)

if changed['boc'] == 0 and changed['size'] == 0:
    sys.exit("Found no burst settings outside comments; aborting without changes.")

open(path, 'w').write(out)
print(f"Set burst-on-connect=0 ({changed['boc']} occurrence(s)), "
      f"burst-size=0 ({changed['size']} occurrence(s)), duplicates collapsed.")
PY

if [ $? -ne 0 ]; then
  echo "Edit failed - restoring backup." >&2
  cp -a "$BACKUP" "$CONF"
  exit 1
fi

# Validate BEFORE the service ever sees it.
if ! python3 -c "import xml.etree.ElementTree as ET,sys; ET.parse(sys.argv[1])" "$CONF"; then
  echo "Edited config is not well-formed XML - restoring backup, service untouched." >&2
  cp -a "$BACKUP" "$CONF"
  exit 1
fi
echo "XML well-formed."

echo "Restarting icecast2 (all zones briefly silent)..."
systemctl restart icecast2

if ! wait_for_icecast; then
  echo "icecast2 did not come up - restoring backup and restarting." >&2
  cp -a "$BACKUP" "$CONF"
  systemctl restart icecast2
  wait_for_icecast || echo "icecast2 still down after restore - check 'journalctl -u icecast2'." >&2
  restart_encoders
  exit 1
fi
echo "icecast2 listening."

restart_encoders
echo "Encoders restarted. Waiting for all 5 mounts..."
for _ in $(seq 1 30); do
  c=$(mount_count)
  if [ "$c" = "5" ]; then
    echo "All 5 mounts up. Done."
    grep -c '<burst-size>0</burst-size>' "$CONF" >/dev/null
    exit 0
  fi
  sleep 2
done

echo "WARNING: only $(mount_count)/5 mounts came back." >&2
echo "Check 'systemctl status alsa-cast@*'. To undo: sudo bash $0 --revert" >&2
exit 1
