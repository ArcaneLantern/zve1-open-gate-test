#!/bin/bash
# ZV-E1 (firmware 2.02): apply the default state: 3840x2560 open gate, the screen at 3:2 and the C2 preview cycle (six steps, the first one the raw write buffer, then one read-only session). This version is not yet run on a ZV-E1.
# WRITES into the camera's memory (not firmware, not settings). A cold boot (battery out for 10 seconds) returns it to stock.
cd "$(dirname "$0")" || exit 1
exec "$PWD/run.sh" apply apply "$@"
