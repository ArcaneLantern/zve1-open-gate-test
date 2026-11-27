"""Build, emulate, verify, and compile Phase 1: PAL 25p Open Gate (MODE_ID = 0x820, index 10)
for Sony ZV-E1 firmware 2.02 (RAM-only).

Creates (all inside zve1fw\\pal25\\):
  - ogsq_zv_pal25_v1.json
  - expected_sites_ogsq_zv_pal25_v1.h
  - libJit_zv_L5_pal25.so
  - libJit_zv_L6_pal25.so
"""
import hashlib
import json
import struct
import subprocess
import sys
from pathlib import Path

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_THUMB, UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_C1_C0_2, UC_ARM_REG_FPEXC, UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_SP

PAL25_DIR = Path(r"zve1fw\pal25")
CPAPP_PATH = Path(r"zve1fw\bins\cpapp-b.bin")
CPAPP_SHA256 = "8e1ee4c48ee1c94c9edd6fe71f6633b7ba689d71ca4998feb1a421bf7b49de2a"
LIBSENCORE_PATH = Path(r"zve1fw\out\firmware.tar_unpacked\0700_part_image\dev\nflasha15_unpacked\lib\libsencore.so")

REPO_ROOT = Path(__file__).resolve().parents[3]
ZV_REF_PATH = REPO_ROOT / r"windows\tools\camera_tests\CT6_memory_read_check\helper_zv\zv_reference.json"
OGSQ_V2_PATH = REPO_ROOT / r"windows\tools\modding\designs\ogsq_zv_v2.json"
PAL_DUMP_PATH = REPO_ROOT / r"windows\camera_private\CT6_20261125T201928Z_zv_check\readcheck_result.txt"
READCHECK_C = REPO_ROOT / r"windows\tools\camera_tests\CT6_memory_read_check\helper\readcheck.c"

BUILD = "zve1_202"
BASE = 0x108000
LOG = 0xB268AC
CTOR_ADDR = 0x96DCF2
CALC_ADDR = 0x96FE16
REC_BASE = 0x25D9FA4
REC_SIZE = 0x170
NMODES = 39
DATA_LO = 0xD00000

MODE = 0x820
INDEX = 10
SRC = 36  # 0xe011

T = {
    "ids": 0xDCC524,
    "colmap": 0xDCDD00,
    "rx": 0xDCCD10,
    "rx2": 0xDCD634,
    "d": 0xDCD8A4,
    "tim": 0xDCCEE4,
    "tim_b": 0xDCCEE4 + 0x3A8,
    "win": 0xEB6292,
    "st1": 0xEB685C,
    "lc": 0xEB6E26,
    "crop": 0xDCC5C0,
    "rl": 0xEB7048,
    "geo": 0xD7BF68,
}
ROW = {
    "colmap": 8,
    "rx": 12,
    "rx2": 16,
    "d": 28,
    "tim": 24,
    "tim_b": 24,
    "win": 38,
    "st1": 38,
    "lc": 14,
    "crop": 20,
    "rl": 16,
    "geo": 12,
}
UNITS = {"59.94 system": 1201200, "50 system": 1440000}
TIMING = {
    "tim": (313, 3836, 137, 19, 287, 4172, 149, 137, "59.94 system"),
    "tim_b": (313, 4600, 23, 1, 287, 5004, 139, 107, "50 system"),
}
RECS = {"L": 0xD35F14, "R": 0xD36ACC}


def run_calc(img: bytes, hz_flag: int, patches=None, fill_byte: int = 0x00):
    buf = bytearray(img)
    if patches:
        for addr, bs in patches:
            off = addr - BASE
            buf[off : off + len(bs)] = bs

    mu = Uc(UC_ARCH_ARM, UC_MODE_THUMB)
    # 0x00100000 .. 0x03000000 (image at 0x108000, BSS zeroed including rounding mode 0x19e1418, records at 0x25d9fa4)
    mu.mem_map(0x00100000, 0x03000000 - 0x00100000)
    mu.mem_write(BASE, bytes(buf))
    mu.mem_write(REC_BASE, bytes([fill_byte]) * (NMODES * REC_SIZE))

    # Stack and scratch object at 0x08000000 (2 MB)
    mu.mem_map(0x08000000, 0x00200000)
    mu.mem_write(0x08000000, bytes([fill_byte]) * 0x00200000)

    # Stop page
    mu.mem_map(0x09000000, 0x1000)

    # Enable VFP
    mu.reg_write(UC_ARM_REG_C1_C0_2, 0x00F00000)
    mu.reg_write(UC_ARM_REG_FPEXC, 0x40000000)

    logs = []

    def hook_log(uc, address, size, user_data):
        logs.append((hex(address), hex(uc.reg_read(UC_ARM_REG_LR)), hex(uc.reg_read(UC_ARM_REG_R0))))
        uc.reg_write(UC_ARM_REG_R0, 0)
        uc.reg_write(UC_ARM_REG_PC, uc.reg_read(UC_ARM_REG_LR))

    mu.hook_add(UC_HOOK_CODE, hook_log, begin=LOG, end=LOG + 2)

    OBJ, SP, STOP = 0x08010000, 0x081F0000, 0x09000000
    mu.reg_write(UC_ARM_REG_R0, OBJ)
    mu.reg_write(UC_ARM_REG_SP, SP)
    mu.reg_write(UC_ARM_REG_LR, STOP | 1)
    mu.emu_start(CTOR_ADDR | 1, STOP, count=500000)

    param_ptr = struct.unpack("<I", mu.mem_read(OBJ + 0x684, 4))[0]
    cfg_ptr = OBJ + 0x54C
    mu.reg_write(UC_ARM_REG_R0, param_ptr)
    mu.reg_write(UC_ARM_REG_R1, hz_flag)
    mu.reg_write(UC_ARM_REG_R2, cfg_ptr)
    mu.reg_write(UC_ARM_REG_SP, SP)
    mu.reg_write(UC_ARM_REG_LR, STOP | 1)
    mu.emu_start(CALC_ADDR | 1, STOP, count=20000000)

    ids = struct.unpack_from(f"<{NMODES}I", buf, T["ids"] - BASE)
    recs = {mid: (i, bytes(mu.mem_read(REC_BASE + i * REC_SIZE, REC_SIZE))) for i, mid in enumerate(ids)}
    return recs, logs


def trow(h, v, p, e):
    return struct.pack("<3I", h, v, 1 | (p << 8) | (e << 16)) * 2


def build_pal25_cells(img: bytes):
    at = lambda t, i=INDEX: T[t] + ROW[t] * i
    rd = lambda a, n: img[a - BASE : a - BASE + n]
    ids = struct.unpack_from(f"<{NMODES}I", img, T["ids"] - BASE)
    assert ids[INDEX] == MODE and ids[SRC] == 0xE011 and NMODES == 39

    out = []

    def cell(label, addr, new, note, old=None):
        cur = rd(addr, len(new))
        assert old is None or cur == old, (label, cur.hex(), old.hex())
        assert cur != new, f"{label}: old already equals new"
        out.append((label, addr, cur, new, note))

    def as_source(label, table, lo, hi, note):
        a, b = rd(at(table) + lo, hi - lo), rd(at(table, SRC) + lo, hi - lo)
        k = 0
        while k < len(a):
            if a[k] == b[k]:
                k += 1
                continue
            j = k
            while j < len(a) and (a[j] != b[j] or (j + 1 < len(a) and a[j + 1] != b[j + 1])):
                j += 1
            k0, j1 = k & ~1, (j + 1) & ~1
            cell(f"{label}+{lo + k0:#x}", at(table) + lo + k0, b[k0:j1], note)
            k = j1

    assert rd(at("colmap"), 8) == struct.pack("<2I", 11, 3) and rd(at("colmap", SRC), 8) == struct.pack("<2I", 1, 3)
    cell(
        "C",
        at("colmap"),
        struct.pack("<I", 1),
        "column map: register matrix column 11 (the 16:9 band) -> 1 (full height), as 0xe011",
        struct.pack("<I", 11),
    )
    assert rd(at("rx"), 8) == struct.pack("<2I", 6, 3) and rd(at("rx", SRC), 8) == struct.pack("<2I", 0, 2)
    as_source("R1", "rx", 0, 12, "receiver type: 6, 3 -> 0, 2, as 0xe011 (12-bit link)")
    as_source("R2", "rx2", 0, 16, "receiver type, second table: 6, 3 -> 0, 2")
    as_source("D", "d", 4, 6, "0xdcd8a4 +4: 478 -> 484, the value of the modes on sensor mode 0x01")
    for t, (h, v, p, e, h0, v0, p0, e0, system) in TIMING.items():
        assert h * v + (v // p) * e == UNITS[system]
        assert h0 * v0 + (v0 // p0) * e0 == UNITS[system]
        assert v % p == 0 and v % 4 == 0
        assert 0 < e < p and v >= 2998
        cell(
            f"T.{t}",
            at(t),
            trow(h, v, p, e),
            f"timing row, {system}: {h0}, {v0}, P {p0}, E {e0} -> {h}, {v}, P {p}, E {e} ({36e6 / UNITS[system]:.4f} fps)",
            trow(h0, v0, p0, e0),
        )
    as_source("W", "win", 0, 38, "stream-0 window row: 0xe011's (top margins 38, 6 -> 122, 22; height 2392 -> 2832)")
    as_source("A", "st1", 0, 38, "aux stream-1 row: 0xe011's")
    as_source("LC", "lc", 0, 14, "LC row: 0xe011's (V offset 220 -> 0, field 6 235 -> 37)")
    as_source("CR", "crop", 0, 20, "crop row: 0xe011's (V offset 220 -> 0, last field 2 -> 0)")
    assert rd(at("geo"), 12) == bytes.fromhex("2008000000000000a201dc00")
    cell(
        "G",
        at("geo") + 10,
        struct.pack("<H", 0),
        "geometry row of 0x820: V offset 220 -> 0 (field +8 = 418 left alone)",
        struct.pack("<H", 220),
    )
    assert struct.unpack_from("<8H", img, at("rl") - BASE) == (16, 1, 2, 8, 1000, 0, 618, 618)
    cell(
        "L",
        at("rl") + 12,
        struct.pack("<2H", 728, 728),
        "read-out table: row fields 618 -> 728 (2832 / 4 + 20)",
        struct.pack("<2H", 618, 618),
    )

    assert len(out) == 19, f"expected 19 cells, got {len(out)}"
    spans = sorted((a, len(n)) for _, a, _, n, _ in out)
    assert all(a + n <= b for (a, n), (b, _) in zip(spans, spans[1:])), "cells overlap"
    return out


def generate_sites_header(img: bytes, design: dict, name: str):
    image_end = BASE + len(img)
    hx = lambda b: ", ".join("0x%02x" % x for x in b)
    sites = sorted((int(p["addr"], 16), bytes.fromhex(p["old"]), bytes.fromhex(p["new"])) for p in design["patches"])
    out = [
        f"/* Generated by build_og_pal25_zv.py from {name}.json (ZV-E1 2.02). Do not edit. */",
        "/* %d sites, %d bytes. Stock bytes were compared with cpapp-b.bin %s. */"
        % (len(sites), sum(len(o) for _, o, _ in sites), design["artifact_sha256"][:16]),
    ]
    rows = []
    for k, (a, old, new) in enumerate(sites):
        assert len(old) == len(new) and old != new and img[a - BASE : a - BASE + len(old)] == old
        lo, hi = a & ~63, (a + len(old) + 63) & ~63
        assert hi - lo <= 4096 and DATA_LO <= lo and hi <= image_end, f"span outside image tables: {hex(a)}"
        for tag, data in (("old", old), ("new", new)):
            out.append("static const u8 site%d_%s[%d] = { %s };" % (k, tag, len(data), hx(data)))
        rows.append("    { 0x%x, %d, site%d_old, site%d_new, 0, 0 }," % (a, len(old), k, k))
    assert all(a + len(o) <= b for (a, o, _), (b, _, _) in zip(sites, sites[1:])), "sites overlap"

    assert design["record_size"] == REC_SIZE
    r_stock = bytes.fromhex(design["stored_record"]["stock"])
    r_new = bytes.fromhex(design["stored_record"]["design"])
    offs = [k for k in range(REC_SIZE) if r_stock[k] != r_new[k]]
    assert len(r_stock) == len(r_new) == REC_SIZE
    assert len(offs) == 64 and offs[:2] == [6, 7] and r_stock[6] == r_stock[7] == 1 and 2 < len(offs) <= 128

    assert len(sites) == 21
    assert design["mode_id"] == "0x820"
    out += [
        "static const unsigned short rec_offs[%d] = { %s };" % (len(offs), ", ".join("0x%x" % k for k in offs)),
        "static const u8 rec_stock[%d] = { %s };" % (len(offs), hx(bytes(r_stock[k] for k in offs))),
        "static const u8 rec_new[%d] = { %s };" % (len(offs), hx(bytes(r_new[k] for k in offs))),
        "#define REC_BYTES %d" % len(offs),
        '#define SITES_TEXT "%d"' % len(sites),
        '#define ALL_TEXT "%d"' % (len(sites) + 1),
        "#define MODE_ID %sU" % design["mode_id"],
        '#define MODE_TEXT "%s"' % design["mode_id"],
        "/* offs: null for a site whose `length` bytes all change; else the offsets, inside `length` bytes, of the noffs bytes that change. */",
        "struct cp_site { u64 address; u32 length; const u8 *stock; const u8 *changed; const unsigned short *offs; u32 noffs; };",
        "static const struct cp_site cp_sites[] = {",
    ] + rows + ["};"]

    hdr_path = PAL25_DIR / f"expected_sites_{name}.h"
    hdr_path.write_text("\n".join(out) + "\n", encoding="utf8", newline="\n")
    return hdr_path, len(sites), len(offs)


def compile_libraries(name: str):
    assert LIBSENCORE_PATH.is_file(), f"Missing {LIBSENCORE_PATH}"
    assert READCHECK_C.is_file(), f"Missing {READCHECK_C}"
    py = sys.executable
    built = {}
    for lvl in (5, 6):
        out_so = PAL25_DIR / f"libJit_zv_L{lvl}_pal25.so"
        cmd = [
            py,
            "-m",
            "ziglang",
            "cc",
            "-target",
            "aarch64-linux-gnu",
            "-std=gnu11",
            "-O1",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-fPIC",
            "-shared",
            "-nostdlib",
            "-ffreestanding",
            "-fno-stack-protector",
            "-fno-builtin",
            "-fno-asynchronous-unwind-tables",
            "-Wl,-soname,libJit.so",
            "-Wl,--no-undefined",
            "-Wl,-z,now",
            "-g0",
            "-s",
            "-Wl,-z,max-page-size=4096",
            "-I",
            str(PAL25_DIR),
            f"-DLEVEL={lvl}",
            f'-DSITES_H="expected_sites_{name}.h"',
            f'-DDESIGN_LABEL="{name}"',
            "-DIMAGER=0x17f1f64UL",
            "-DCTRL_DRVPARAM=0x684U",
            "-DREC=0x170U",
            str(READCHECK_C),
            str(LIBSENCORE_PATH),
            "-o",
            str(out_so),
        ]
        res = subprocess.run(cmd, capture_output=True, text=True)
        if res.returncode != 0:
            print("STDOUT:", res.stdout)
            print("STDERR:", res.stderr)
            raise RuntimeError(f"ziglang cc failed for LEVEL={lvl}")
        data = out_so.read_bytes()
        assert 0 < len(data) <= 65520, f"{out_so} size {len(data)} out of range"
        sha = hashlib.sha256(data).hexdigest()
        built[lvl] = (out_so, len(data), sha)
        print(f"BUILT {out_so.name}: size={len(data)} bytes (<= 65520), sha256={sha}")
    return built


def main():
    PAL25_DIR.mkdir(parents=True, exist_ok=True)
    img = CPAPP_PATH.read_bytes()
    sha = hashlib.sha256(img).hexdigest()
    assert sha == CPAPP_SHA256, f"cpapp-b.bin SHA-256 mismatch: {sha}"

    og_v2 = json.loads(OGSQ_V2_PATH.read_text(encoding="utf8"))
    zv_ref = json.loads(ZV_REF_PATH.read_text(encoding="utf8"))

    # Assert 1: run_calc(img, hz_flag=0) matches ALL 39 modes in zv_reference.json with 0 diffs
    recs0, logs0 = run_calc(img, 0)
    assert not logs0, f"Assert 1 logs: {logs0}"
    ref_recs = zv_ref["emulated_stock_records"]
    assert len(ref_recs) == NMODES
    for k, hexval in ref_recs.items():
        mid = int(k, 16)
        assert recs0[mid][1] == bytes.fromhex(hexval), f"Assert 1 mismatch at mode {k}"
    print("PASS Assert 1: hz=0 matches all 39 stock records in zv_reference.json (0 diffs, 0 logs)")

    # Assert 2: run_calc(img, hz_flag=0, ogsq_zv_v2_sensor_cells) + d[6:8]=(16,19) matches ogsq_zv_v2 design with 0 diffs
    og_cells_s = [(int(p["addr"], 16), bytes.fromhex(p["new"])) for p in og_v2["patches"] if p["kind"] == "S"]
    recs0_og, logs0_og = run_calc(img, 0, og_cells_s)
    assert not logs0_og, f"Assert 2 logs: {logs0_og}"
    d8c0 = bytearray(recs0_og[0x8C0][1])
    d8c0[6], d8c0[7] = 16, 19
    assert bytes(d8c0) == bytes.fromhex(og_v2["stored_record"]["design"]), "Assert 2 mismatch vs ogsq_zv_v2 design"
    print("PASS Assert 2: hz=0 with ogsq_zv_v2 S-cells matches ogsq_zv_v2 stored_record.design (0 diffs, 0 logs)")

    # Assert 3: run_calc(img, hz_flag=1) matches real camera PAL stock 0x8c0 on all initialized bytes
    recs1_00, logs1_00 = run_calc(img, 1, fill_byte=0x00)
    recs1_AA, logs1_AA = run_calc(img, 1, fill_byte=0xAA)
    recs1_55, logs1_55 = run_calc(img, 1, fill_byte=0x55)
    assert not (logs1_00 or logs1_AA or logs1_55), "Assert 3 unexpected logs"
    uninit_8c0 = {
        o
        for o in range(REC_SIZE)
        if not (recs1_00[0x8C0][1][o] == recs1_AA[0x8C0][1][o] == recs1_55[0x8C0][1][o])
    }
    pal_line = next(
        ln.split()[2]
        for ln in PAL_DUMP_PATH.read_text(encoding="utf8").splitlines()
        if ln.startswith("other stored_record ")
    )
    cam_pal_8c0 = bytes.fromhex(pal_line)
    assert len(cam_pal_8c0) == REC_SIZE
    init_diffs_8c0 = [
        o for o in range(REC_SIZE) if o not in uninit_8c0 and recs1_00[0x8C0][1][o] != cam_pal_8c0[o]
    ]
    assert not init_diffs_8c0, f"Assert 3 initialized byte diffs vs real camera PAL dump: {[hex(x) for x in init_diffs_8c0]}"
    print(f"PASS Assert 3: hz=1 0x8c0 matches real ZV-E1 PAL dump on all {REC_SIZE - len(uninit_8c0)} initialized bytes (0 diffs; {len(uninit_8c0)} padding bytes)")

    # Assert 4: PAL 25p (0x820, index 10) 19 sensor cells + hz=1 emulation + zero padding overlap
    cs = build_pal25_cells(img)
    patches_s = [(a, n) for _, a, _, n, _ in cs]

    s00, ls0 = run_calc(img, 1, None, fill_byte=0x00)
    sAA, lsA = run_calc(img, 1, None, fill_byte=0xAA)
    s55, ls5 = run_calc(img, 1, None, fill_byte=0x55)
    n00, ln0 = run_calc(img, 1, patches_s, fill_byte=0x00)
    nAA, lnA = run_calc(img, 1, patches_s, fill_byte=0xAA)
    n55, ln5 = run_calc(img, 1, patches_s, fill_byte=0x55)
    assert not (ls0 or lsA or ls5 or ln0 or lnA or ln5), "Assert 4 unexpected logs"

    for mid in s00:
        if mid != MODE:
            assert s00[mid][1] == n00[mid][1], f"Assert 4 changed other mode {hex(mid)}"

    s_rec = s00[MODE][1]
    assert s00[MODE][0] == n00[MODE][0] == INDEX
    assert len(s_rec) == REC_SIZE and s_rec[4:8] == b"\x01\x01\x01\x01"

    uninit_s = {o for o in range(REC_SIZE) if not (s00[MODE][1][o] == sAA[MODE][1][o] == s55[MODE][1][o])}
    uninit_n = {o for o in range(REC_SIZE) if not (n00[MODE][1][o] == nAA[MODE][1][o] == n55[MODE][1][o])}
    assert len(uninit_s) == 30 and uninit_s == uninit_n, (len(uninit_s), uninit_s ^ uninit_n)

    d_rec = bytearray(n00[MODE][1])
    d_rec[6], d_rec[7] = 16, 19
    rec_offs = [o for o in range(REC_SIZE) if s_rec[o] != d_rec[o]]
    assert len(rec_offs) == 64 and rec_offs[:2] == [6, 7], (len(rec_offs), rec_offs[:5])
    assert not any(o in (uninit_s | uninit_n) for o in rec_offs), "Assert 4 padding overlap!"
    print(f"PASS Assert 4: 0x820 PAL 25p 19 S-cells -> hz=1 record has {len(rec_offs)} diffs, 0 other modes changed, 0 padding overlap (30 padding offsets)")

    # Take picture-record patches (0xd35f14, 0xd36acc) from ogsq_zv_v2.json and verify against cpapp-b.bin
    rec_patches = [p for p in og_v2["patches"] if p["kind"] == "R"]
    assert len(rec_patches) == 2 and {int(p["addr"], 16) for p in rec_patches} == set(RECS.values())
    for p in rec_patches:
        addr = int(p["addr"], 16)
        old_b = bytes.fromhex(p["old"])
        assert len(old_b) == 3000 and img[addr - BASE : addr - BASE + 3000] == old_b

    patches = [
        {"kind": "S", "addr": hex(a), "old": o.hex(), "new": n.hex(), "note": f"{lab} {note}", "where": "file"}
        for lab, a, o, n, note in cs
    ] + rec_patches

    name = "ogsq_zv_pal25_v1"
    design = {
        "design": name,
        "build": BUILD,
        "camera": "ZV-E1, firmware 2.02",
        "title": "PAL 25p full height in drive mode 0x820 through the sensor's full-height mode (matrix column 1, as 0xe011), first-stage window of 2848 rows squeezed by Lrc into the stock picture, picture records set for the 12-bit link",
        "status": "built from cpapp-b.bin 2.02 and verified via Unicorn emulation (coprocessor calculator + AArch64 ELF execution); not yet run on live camera",
        "artifact": "cpapp-b.bin",
        "artifact_sha256": sha,
        "generated_by": "build_og_pal25_zv.py",
        "ported_from": {"design": "ogsq_zv_v2", "build": BUILD},
        "mode_id": hex(MODE),
        "mode_index": INDEX,
        "hz_flag": 1,
        "sensor_mode_taken_from": f"0xe011 (index {SRC})",
        "records_base": hex(REC_BASE),
        "record_size": REC_SIZE,
        "timing": {
            k: {
                "hmax": t[0],
                "vmax": t[1],
                "p": t[2],
                "e": t[3],
                "units": UNITS[t[8]],
                "fps": round(36e6 / UNITS[t[8]], 6),
                "system": t[8],
            }
            for k, t in TIMING.items()
        },
        "summary": {
            "sites": len(patches),
            "bytes": sum(len(p["new"]) // 2 for p in patches),
            "sensor_cells": len(cs),
            "records": 2,
        },
        "lrc": og_v2["lrc"],
        "link_words": og_v2["link_words"],
        "patches": patches,
        "stored_record": {
            "address": hex(REC_BASE + INDEX * REC_SIZE),
            "stock": s_rec.hex(),
            "design": bytes(d_rec).hex(),
            "offsets_that_differ": [hex(o) for o in rec_offs],
            "uninitialized_padding_offsets": [hex(o) for o in sorted(uninit_s)],
        },
    }

    json_path = PAL25_DIR / f"{name}.json"
    json_path.write_text(json.dumps(design, indent=1) + "\n", encoding="utf8", newline="\n")
    print(f"Wrote {json_path}")

    hdr_path, n_sites, n_rec_bytes = generate_sites_header(img, design, name)
    print(f"Wrote {hdr_path} ({n_sites} sites, {n_rec_bytes} rec bytes)")

    built = compile_libraries(name)
    for lvl, (p, sz, h) in sorted(built.items()):
        print(f"SUMMARY L{lvl}_pal25: {p} | {sz} bytes | {h}")


if __name__ == "__main__":
    main()
