#!/bin/bash
# ZV-E1 (firmware 2.02): TEST (NOT RUN ON A CAMERA YET): the new sensor step alone with the proven 3840x2560 output and encoder steps, the screen at 3:2 and C2.
# WRITES into the camera's memory (not firmware, not settings). A cold boot (battery out for 10 seconds) returns it to stock.
cd "$(dirname "$0")" || exit 1
exec "$PWD/run.sh" apply realrows "$@"
