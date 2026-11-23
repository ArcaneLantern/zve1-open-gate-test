#!/bin/bash
# ZV-E1 (firmware 2.02): apply only the four open-gate steps (raw write buffer, sensor, output size, encoder), without the two screen steps.
# WRITES into the camera's memory (not firmware, not settings). A cold boot (battery out for 10 seconds) returns it to stock.
cd "$(dirname "$0")" || exit 1
exec "$PWD/run.sh" apply apply --no-screen "$@"
