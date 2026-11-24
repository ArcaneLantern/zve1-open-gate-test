#!/bin/bash
# ZV-E1 (firmware 2.02): apply the default state: 3840x2560 open gate, file headers 3840x2560 (no remux needed), the screen at 3:2 and the C2 preview cycle (six steps, the first one the raw write buffer, then one read-only session).
# WRITES into the camera's memory (not firmware, not settings). A cold boot (battery out for 10 seconds) returns it to stock.
# Extra options are passed on, e.g.  --no-meta  --dry-run. Cold boot with the battery out before running, and set Proxy Recording to Off.
# The power switch alone removes open gate but not the header height: pull the battery before recording 16:9 again.
cd "$(dirname "$0")" || exit 1
exec "$PWD/run.sh" apply apply "$@"
