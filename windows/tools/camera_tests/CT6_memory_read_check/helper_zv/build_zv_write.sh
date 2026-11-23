#!/bin/bash
# Build the twelve ZV-E1 2.02 write libraries from the A7 IV helper's source (helper/readcheck.c), with this build's tables and constants
# (ZV-E1 port of the A7S III kit, 2026-11-24). Run gen_zv_write.py first.
# usage: build_zv_write.sh        (writes libJit_zv_<step>.so into this folder and prints SHA-256, size, step)
# Flags are those of helper/rebuild.sh. Differences from an A7 IV build: the headers of gen_zv_write.py, the ZV-E1 libsencore.so to link
# against, and these constants (modding/ZVE1_PORT.md):
#   L13/L14  (added 2026-11-24 after the first camera test) the DMM server's page of pointers 0x19cf000: workspace +0x8f0, unit objects +0x444
#            (= A7C II 0x1a8c558 / 0x1a8c0ac); the one word of dmmwb_zv_v1 (the movie raw write buffer's size), with texts for one word
#   L5/L6    IMAGER 0x17f1f64 (0x96bce6 returns it; = A7S III 0x12a41f0, A7C II 0x18aeb8c), drive-parameter pointer at control +0x684
#            (as the A7C II: 27 accesses, the first in the constructor block), stored record 0x170 bytes (0x96f2c4)
#   L19/L20, C19/C20   av-cam.bin at physical 0x401000000 (kemco.txt, byte-identical to the A7C II's)
# Steps as in the A7S III kit: L = open gate (5/6 sensor side, 16/17 output size, 19/20 encoder side), S = screen words (16/17),
# C = the C2 preview routine in appFw.so (19/20).
set -e
H="$(cd "$(dirname "$0")" && pwd)"
SEN="$H/../../../work/extracted/zve1_202/0700_part_image/dev/nflasha15/lib/libsencore.so"
cd "$H/../helper"
CC=(../../../work/venv_zig/Scripts/python.exe -m ziglang cc -target aarch64-linux-gnu -std=gnu11 -O1 -Wall -Wextra -Werror -fPIC -shared -nostdlib -ffreestanding
    -fno-stack-protector -fno-builtin -fno-asynchronous-unwind-tables -Wl,-soname,libJit.so -Wl,--no-undefined -Wl,-z,now -g0 -s -Wl,-z,max-page-size=4096)
for L in 5 6; do
  "${CC[@]}" -DLEVEL=$L '-DSITES_H="expected_sites_ogsq_zv_v2.h"' '-DDESIGN_LABEL="ogsq_zv_v2"' -DIMAGER=0x17f1f64UL -DCTRL_DRVPARAM=0x684U -DREC=0x170U \
    readcheck.c "$SEN" -o "$H/libJit_zv_L$L.so"
done
for L in 13 14; do
  "${CC[@]}" -DLEVEL=$L '-DDMM_SITES_H="expected_dmm_dmmwb_zv_v1.h"' -DDMM_GLOBALS=0x019cf000UL -DG_WORKSPACE=0x8f0U -DG_UNITS=0x444U \
    '-DDMM_WORDS_TEXT="the memory-manager word (the movie raw write buffer size)"' '-DDMM_DONE_TEXT="the site holds"' \
    '-DDMM_RECS_TEXT="the record and its parent'"'"'s are as in the file; a unit of the new size fits"' \
    '-DDMM_NOFIT_TEXT="a unit of the new size does not fit the parent"' readcheck.c "$SEN" -o "$H/libJit_zv_L$L.so"
done
for L in 16 17; do
  "${CC[@]}" -DLEVEL=$L '-DWORDS_H="expected_words_outsz2560_zv_v1.h"' readcheck.c "$SEN" -o "$H/libJit_zv_L$L.so"
  "${CC[@]}" -DLEVEL=$L '-DWORDS_H="expected_words_lcdfill_zv_v2.h"' readcheck.c "$SEN" -o "$H/libJit_zv_S$L.so"
done
for L in 19 20; do
  "${CC[@]}" -DLEVEL=$L '-DMP_H="expected_mp_ogfile2560_hs_s_zv_v1.h"' -DAVCAM_PHYS=0x401000000UL readcheck.c -o "$H/libJit_zv_L$L.so"
  "${CC[@]}" -DLEVEL=$L '-DMP_H="expected_mp_lcdcycle_zv_v1.h"' -DAVCAM_PHYS=0x401000000UL readcheck.c -o "$H/libJit_zv_C$L.so"
done
cd "$H"
for N in L13 L14 L5 L6 L16 L17 L19 L20 S16 S17 C19 C20; do echo "$(sha256sum libJit_zv_$N.so | cut -d' ' -f1) $(stat -c %s libJit_zv_$N.so) $N"; done
