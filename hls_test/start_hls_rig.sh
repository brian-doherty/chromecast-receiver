#!/bin/bash
# Stands up the A/B latency rig: packed-ADTS HLS vs progressive MP3.
#
# Both legs carry an identical generated source - a 1 kHz beep for the first
# 80ms of every second, silence otherwise - so "first audible" is unambiguous
# to a listener and lands within 1s of true playback start.
#
# Nothing here touches ALSA, so cast_arbitrator.py (which polls
# /proc/asound playback substreams) never sees it and will not interfere.
# Production encoders and mounts are untouched; the MP3 leg is a 6th Icecast
# source, within the configured <sources>10</sources>. No root needed.
#
# Corrections learned the hard way:
#   - MPEG-TS segments are rejected outright by Chromecast Audio. Packed ADTS
#     (.aac) works. Only the ADTS leg is started here.
#   - A 6-second live window is far too short: a player that falls even
#     slightly behind drops off the back of the playlist and re-polls forever
#     without ever fetching a segment. 2s segments x 30 = a 60s window.
#   - Segments and playlist need CORS headers and correct MIME types; see
#     hls_server.py.

set -u

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEB="${DIR}/web/aac"
PORT=8099
HOST_IP=192.168.7.1

SRC='aevalsrc=0.4*sin(2*PI*1000*t)*lt(mod(t\,1)\,0.08):s=44100:c=stereo'

mkdir -p "$WEB"
rm -f "$WEB"/*.aac "$WEB"/*.m3u8

echo "=== HLS leg: packed ADTS, 2s segments, 60s window ==="
(setsid nohup ffmpeg -hide_banner -loglevel error -re \
  -f lavfi -i "$SRC" \
  -c:a aac -b:a 192k \
  -f segment -segment_time 2 -segment_format adts \
  -segment_list "${WEB}/stream.m3u8" -segment_list_type m3u8 \
  -segment_list_size 30 -segment_list_flags +live -segment_wrap 300 \
  "${WEB}/seg%05d.aac" \
  > "${DIR}/aac.log" 2>&1 < /dev/null &)

echo "=== MP3 baseline leg: Icecast scratch mount /beeptest.mp3 ==="
(setsid nohup ffmpeg -hide_banner -loglevel error -re \
  -f lavfi -i "$SRC" \
  -c:a libmp3lame -b:a 192k \
  -content_type audio/mpeg -f mp3 \
  "icecast://source:${ICECAST_SOURCE_PASSWORD}@localhost:8000/beeptest.mp3" \
  > "${DIR}/mp3.log" 2>&1 < /dev/null &)

echo "=== CORS/MIME static server on :${PORT} ==="
(setsid nohup python3 -u "${DIR}/hls_server.py" "$PORT" "${DIR}/web" \
  > "${DIR}/http.log" 2>&1 < /dev/null &)

echo
echo "HLS URL : http://${HOST_IP}:${PORT}/aac/stream.m3u8"
echo "MP3 URL : http://${HOST_IP}:8000/beeptest.mp3"
