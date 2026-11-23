#!/bin/bash
# ZV-E1 (firmware 2.02): put back only the two screen steps (press C2 until the screen is at 3:2 first).
# WRITES into the camera's memory (not firmware, not settings). A cold boot (battery out for 10 seconds) returns it to stock.
cd "$(dirname "$0")" || exit 1
exec "$PWD/run.sh" apply screen-putback "$@"
