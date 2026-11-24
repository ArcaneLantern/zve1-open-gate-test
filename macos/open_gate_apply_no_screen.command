#!/bin/bash
# ZV-E1 (firmware 2.02): apply only the four open-gate steps (raw write buffer, sensor, output size, encoder with file headers 3840x2560), without the two screen steps.
# WRITES into the camera's memory (not firmware, not settings). A cold boot (battery out for 10 seconds) returns it to stock.
# Extra options are passed on, e.g.  --no-meta  --dry-run. Cold boot with the battery out before running, and set Proxy Recording to Off.
# The power switch alone can leave the encoder side at 2560 (a 4K clip then came out 3840x2560, 16:9 picture letterboxed): pull the battery before normal 4K.
cd "$(dirname "$0")" || exit 1
exec "$PWD/run.sh" apply apply --no-screen "$@"
