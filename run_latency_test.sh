#!/bin/bash
# Latency test with a matched on-demand starting condition.
#
# The mounts have been up for days, so they have a full Icecast burst window
# ready and would start almost instantly - which would make every variant look
# good and tell us nothing. Restarting the encoder first reproduces the actual
# on-demand case the system faces in production (finding #6 in CONTEXT.md).
#
# Needs root for systemctl. Run from your own terminal:
#     !sudo bash run_latency_test.sh familyroom
#
# Optional 2nd/3rd args pass through to the python harness, e.g.
#     !sudo bash run_latency_test.sh familyroom --app stock
#     !sudo bash run_latency_test.sh familyroom --mode direct

set -u

ZONE="${1:?usage: run_latency_test.sh <zone> [--app stock|custom] [--mode caf|direct]}"
shift
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== restarting alsa-cast@${ZONE} to clear the burst window ==="
systemctl restart "alsa-cast@${ZONE}.service"

# Let the encoder reconnect and the mount re-establish, but not long enough to
# accumulate a burst buffer.
sleep 2
systemctl is-active --quiet "alsa-cast@${ZONE}.service" \
  && echo "encoder active" \
  || { echo "encoder failed to start"; exit 1; }

echo
echo "=== casting - LISTEN for the first audible tone ==="
PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION=python \
  python3 "${DIR}/cast_latency_test.py" "${ZONE}" "$@"
