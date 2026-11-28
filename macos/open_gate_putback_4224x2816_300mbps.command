#!/bin/bash
# ZV-E1 (firmware 2.02): put the 4224x2816 state applied at 300 Mbps back to stock (press C2 until the screen is at 3:2 first).
# WRITES into the camera's memory (not firmware, not settings). A cold boot (battery out for 10 seconds) returns it to stock.
cd "$(dirname "$0")" || exit 1
exec "$PWD/run.sh" apply putback4224 --rate300 "$@"
