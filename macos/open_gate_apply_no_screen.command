#!/bin/bash
# ZV-E1 (firmware 2.02): apply only the four open-gate steps (raw write buffer, sensor, output size, encoder with file headers 3840x2560), without the two screen steps.
# WRITES into the camera's memory (not firmware, not settings). A cold boot (battery out for 10 seconds) returns it to stock.
# Extra options are passed on, e.g.  --no-meta  --dry-run. Cold boot with the battery out before running, and set Proxy Recording to Off.
# The power switch alone removes open gate but not the header height: pull the battery before recording 16:9 again.
cd "$(dirname "$0")" || exit 1
exec "$PWD/run.sh" apply apply --no-screen "$@"
