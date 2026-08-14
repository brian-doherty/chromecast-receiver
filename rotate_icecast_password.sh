#!/bin/bash
# Rotate the Icecast source password.
#
# The old password was committed to a public GitHub repo and must be treated
# as compromised. Scrubbing git history does not undo public exposure - the
# repo may already have been cloned, cached, or indexed - so rotation is the
# actual fix, not an optional extra.
#
# Updates both places the password lives:
#   /etc/icecast2/icecast.xml            <source-password>
#   /etc/systemd/system/alsa-cast@.service   ExecStart icecast:// URL
#
# Safety: backs up both files, validates the XML before the service sees it,
# restarts icecast2 and confirms it listens, restarts the five encoders and
# waits for all five mounts. Restores both backups if anything fails.
#
# Expect all zones silent for roughly 5-15s. Encoders are Restart=always with
# RestartSec=5, so they self-heal even if this is interrupted.
#
# Run as root:
#   sudo bash rotate_icecast_password.sh                 # generate a new one
#   sudo bash rotate_icecast_password.sh 'newpassword'   # or supply it
#   sudo bash rotate_icecast_password.sh --revert

set -uo pipefail

CONF=/etc/icecast2/icecast.xml
UNIT=/etc/systemd/system/alsa-cast@.service
CBAK="${CONF}.bak-prerotate"
UBAK="${UNIT}.bak-prerotate"
ZONES=(backyard familyroom livingroom insidehome wholehome)

wait_for_icecast() {
  for _ in $(seq 1 20); do
    curl -sf -m 3 -o /dev/null http://localhost:8000/status-json.xsl && return 0
    sleep 1
  done
  return 1
}

mount_count() {
  curl -sf -m 5 http://localhost:8000/status-json.xsl 2>/dev/null | python3 -c "
import json,sys
try: d=json.load(sys.stdin)['icestats']
except Exception: print(0); sys.exit()
s=d.get('source',[]); s=[s] if isinstance(s,dict) else s
names={x.get('listenurl','').split('/')[-1] for x in s}
want=['backyard.mp3','familyroom.mp3','livingroom.mp3','insidehome.mp3','wholehome.mp3']
print(len([z for z in want if z in names]))
" 2>/dev/null || echo 0
}

restart_all() {
  systemctl daemon-reload
  for z in "${ZONES[@]}"; do systemctl restart "alsa-cast@${z}.service" || true; done
}

restore() {
  echo "Restoring backups..." >&2
  [ -f "$CBAK" ] && cp -a "$CBAK" "$CONF"
  [ -f "$UBAK" ] && cp -a "$UBAK" "$UNIT"
  systemctl daemon-reload
  systemctl restart icecast2
  wait_for_icecast || echo "icecast2 still down after restore - check journalctl -u icecast2" >&2
  restart_all
}

if [ "${1:-}" = "--revert" ]; then
  [ -f "$CBAK" ] || { echo "No backup at $CBAK" >&2; exit 1; }
  restore
  echo "Reverted to the previous password."
  exit 0
fi

NEWPASS="${1:-}"
if [ -z "$NEWPASS" ]; then
  NEWPASS="$(tr -dc 'A-Za-z0-9' </dev/urandom | head -c 28)"
  echo "Generated a new source password."
fi

case "$NEWPASS" in
  *[\'\"\&\<\>@:/]*)
    echo "Password contains a character that is unsafe in XML or a URL." >&2
    echo "Use only letters and digits." >&2
    exit 1 ;;
esac

cp -a "$CONF" "$CBAK"
cp -a "$UNIT" "$UBAK"
echo "Backups at $CBAK and $UBAK"

OLDPASS="$(python3 - "$CONF" <<'PY'
import re, sys
src = open(sys.argv[1]).read()
# Only look outside XML comments.
parts = re.split(r'(<!--.*?-->)', src, flags=re.S)
for p in parts:
    if p.startswith('<!--'):
        continue
    m = re.search(r'<source-password>([^<]*)</source-password>', p)
    if m:
        print(m.group(1).strip())
        break
PY
)"

if [ -z "$OLDPASS" ]; then
  echo "Could not find <source-password> outside comments in $CONF; aborting." >&2
  exit 1
fi

python3 - "$CONF" "$NEWPASS" <<'PY'
import re, sys
path, new = sys.argv[1], sys.argv[2]
src = open(path).read()
parts = re.split(r'(<!--.*?-->)', src, flags=re.S)
n = 0
for i, p in enumerate(parts):
    if p.startswith('<!--'):
        continue
    p, k = re.subn(r'<source-password>[^<]*</source-password>',
                   f'<source-password>{new}</source-password>', p)
    n += k
    parts[i] = p
if n == 0:
    sys.exit("No <source-password> replaced; aborting.")
open(path, 'w').write(''.join(parts))
print(f"Updated <source-password> ({n} occurrence(s)).")
PY
[ $? -eq 0 ] || { restore; exit 1; }

if ! python3 -c "import xml.etree.ElementTree as ET,sys; ET.parse(sys.argv[1])" "$CONF"; then
  echo "Edited icecast.xml is not well-formed - restoring, service untouched." >&2
  restore
  exit 1
fi
echo "XML well-formed."

python3 - "$UNIT" "$OLDPASS" "$NEWPASS" <<'PY'
import sys
path, old, new = sys.argv[1], sys.argv[2], sys.argv[3]
src = open(path).read()
if f"source:{old}@" not in src:
    sys.exit(f"Did not find source:<oldpassword>@ in {path}; aborting.")
open(path, 'w').write(src.replace(f"source:{old}@", f"source:{new}@"))
print("Updated the encoder unit's ExecStart URL.")
PY
[ $? -eq 0 ] || { restore; exit 1; }

echo "Restarting icecast2 (all zones briefly silent)..."
systemctl restart icecast2
if ! wait_for_icecast; then
  echo "icecast2 did not come up." >&2
  restore
  exit 1
fi
echo "icecast2 listening."

restart_all
echo "Encoders restarted. Waiting for all 5 mounts..."
for _ in $(seq 1 30); do
  if [ "$(mount_count)" = "5" ]; then
    echo
    echo "All 5 mounts up. Rotation complete."
    echo "New source password: $NEWPASS"
    echo "Store it in your password manager and in hls_test/.icecast_pass if you"
    echo "want the test rig to work (that path is gitignored)."
    exit 0
  fi
  sleep 2
done

echo "WARNING: only $(mount_count)/5 mounts returned - restoring." >&2
restore
exit 1
