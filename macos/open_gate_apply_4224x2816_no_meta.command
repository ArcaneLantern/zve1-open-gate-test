#!/bin/bash
# ZV-E1 (firmware 2.02): apply the 4224x2816 state without the MP4 header size (headers stay 3840x2160; NOT RUN ON A CAMERA YET). Put back with open_gate_putback_4224x2816.
# WRITES into the camera's memory (not firmware, not settings). A cold boot (battery out for 10 seconds) returns it to stock.
cd "$(dirname "$0")" || exit 1
exec "$PWD/run.sh" apply apply4224 --no-meta "$@"
