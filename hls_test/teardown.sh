#!/bin/bash
# Tear down the HLS test rig. Kills by resolved PID rather than pkill pattern,
# because a pkill pattern also matches the shell running it.
set -u

self=$$
for pat in "segment_format adts" "hls_segment_filename" "beeptest.mp3" "hls_server.py" "http.server 8099"; do
  for pid in $(pgrep -f "$pat" 2>/dev/null); do
    [ "$pid" = "$self" ] && continue
    kill "$pid" 2>/dev/null && echo "killed $pid ($pat)"
  done
done
