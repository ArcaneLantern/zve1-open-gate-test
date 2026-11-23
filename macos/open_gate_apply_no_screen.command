#!/bin/bash
# ZV-E1 (firmware 2.02): apply only the three open-gate steps, without the two screen steps.
# WRITES into the camera's memory (not firmware, not settings). A cold boot (battery out for 10 seconds) returns it to stock.
cd "$(dirname "$0")" || exit 1
exec "$PWD/run.sh" apply apply --no-screen "$@"
