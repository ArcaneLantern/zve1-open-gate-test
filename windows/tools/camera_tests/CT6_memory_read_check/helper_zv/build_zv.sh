#!/bin/bash
# Build the ZV-E1 read-only helper (from helper_s3/build_s3.sh). usage: build_zv.sh check|dump <out file>
# Same pinned flags as helper/rebuild.sh; linked against the ZV-E1 2.02 libsencore.so for its three imports.
set -e
H="$(cd "$(dirname "$0")" && pwd)"
SEN="$H/../../../work/extracted/zve1_202/0700_part_image/dev/nflasha15/lib/libsencore.so"
cd "$H"
case "$1" in
  check) D=0 ;;
  dump) D=1 ;;
  *) echo "usage: build_zv.sh check|dump <out>"; exit 2 ;;
esac
../../../work/venv_zig/Scripts/python.exe -m ziglang cc -target aarch64-linux-gnu -std=gnu11 -O1 -Wall -Wextra -Werror -fPIC -shared -nostdlib -ffreestanding \
  -fno-stack-protector -fno-builtin -fno-asynchronous-unwind-tables -Wl,-soname,libJit.so -Wl,--no-undefined -Wl,-z,now -g0 -s -Wl,-z,max-page-size=4096 \
  -DDUMP=$D zvread.c "$SEN" -o "$2"
echo "$(sha256sum "$2" | cut -d' ' -f1) $(stat -c %s "$2") $1"
