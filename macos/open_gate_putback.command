#!/bin/bash
# ZV-E1 (firmware 2.02): put all six steps back to stock, the file header height included (press C2 until the screen is at 3:2 first).
# WRITES into the camera's memory (not firmware, not settings). A cold boot (battery out for 10 seconds) returns it to stock.
cd "$(dirname "$0")" || exit 1
exec "$PWD/run.sh" apply putback "$@"
