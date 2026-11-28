#!/bin/bash
# ZV-E1 (firmware 2.02): apply the 4224x2816 state with the 100M record settings at 300 Mbps (NOT RUN ON A CAMERA YET). Put back with open_gate_putback_4224x2816_300mbps.
# WRITES into the camera's memory (not firmware, not settings). A cold boot (battery out for 10 seconds) returns it to stock.
cd "$(dirname "$0")" || exit 1
exec "$PWD/run.sh" apply apply4224 --rate300 "$@"
