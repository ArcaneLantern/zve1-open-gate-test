"""Build the ZV-E1 2.02 coprocessor design `ogsq_zv_v2` (or `ogsq_zv_v1`): the A7S III's proven `ogsq_s3_v5`, ported (2026-11-24).

  C:/Python313/python.exe -B build/build_og_zv.py [--name ogsq_zv_v2]          (--name ogsq_zv_v1 rebuilds v1, with its guessed run-time bytes)

v2 (after the first camera test, 2026-11-23) differs from v1 in the stored record only: v1 left two calculated bytes stock (+0x129, +0x15e, from
a guessed list of run-time bytes); v2 holds every calculated byte, and the camera's own run-time bytes (+0x11a/+0x11b) are not touched. The
restart of that test came from the raw write buffer (build/build_dmm_zv.py, design dmmwb_zv_v1), which v2 needs applied first.

The ZV-E1 has the A7S III's IMX510 sensor and drive-mode list (39 modes: the A7S III's 40 without 0x8010; 0x8c0 is still index 12,
0xe011 moves from index 37 to 36) on the A7C II's platform generation. ogsq_s3_v5 is what works on an A7S III (2026-11-22): drive mode
0x8c0 (FF 4K 23.98p) takes the sensor's own full-height mode 0x01 of drive mode 0xe011, and the first stage takes the whole 2,832 rows.
This builds the same thing from the ZV-E1's own tables and records (modding/ZVE1_PORT.md has the address map):

  C  column map 0xdcdd00: column 11 -> 1 (as 0xe011). The second value is 3 on this body for both (A7S III 4); it is not changed
  R  receiver type (0xdccd10, 0xdcd634): 6, 3 -> 0, 2, as 0xe011 (the A7S III's 4K rows hold 5, 3; every 10-bit mode on the ZV-E1 holds 6)
  D  0xdcd8a4 +4: 478 -> 484 (rows identical to the A7S III's)
  T  timing rows: 59.94 system 287, 5220, P 87, E 56 -> 313, 4788, P 57, E 34 (A7S III stock 266, 5628, 67, 53; same frame length
     1,501,500 units); 50 system 268, 5580, 93, 76 -> 313, 4780, 239, 193 (= the A7S III's). Both rows keep E < P (ogsq_s3_v4's rule)
  W, A, LC, CR  window, aux stream, LC and crop rows: 0xe011's (identical to the A7S III's rows)
  G  geometry row of 0x8c0 (0xd7c034): V offset +10 220 -> 0. The ZV-E1's rows have one more field (+8, 418 for 0x8c0, 0 on the
     A7S III): left as it is, NOT KNOWN what it is
  L  read-out table (0xeb7048, 16-byte rows on this body: the A7S III's two frame-length fields are gone): row fields 618 -> 728
  records  the 0x8c0/0x820 picture pair the ZV-E1's selector 0x26f894 returns (0xd35f14 / 0xd36acc), rebuilt with build_og_s3.py's
     model (A7 IV field classes; frame fields from this body's full-height still pair 0xd4264c / 0xd43204; the ZV-E1's own packers),
     stage 2848 rows from active row 0; then the v5 link-format words for a 12-bit link (s3_linkfmt_words.py: the rule holds on all 38
     ZV-E1 records)
  stored record  the ZV-E1's own calculator 0x390fa0 (build/emu_drvparam.py zve1_202, 0x170-byte records) with every cell applied,
     then the vertical sampling ratio 16/19 (+6/+7). The A7S III camera's run-time bytes, moved to this layout, are left out (a guess)
Design only: nothing is written to a firmware file, nothing is sent to a camera. Never run on a ZV-E1.
"""
import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "build"))
import build_og_s3 as V  # noqa: E402
import build_og_s3_v3 as V3  # noqa: E402
import emu_drvparam  # noqa: E402
import gen_block_words as G  # noqa: E402
import s3_linkfmt_words as LF  # noqa: E402

BUILD, BASE, MODE, INDEX, SRC, NMODES = "zve1_202", 0x108000, 0x8C0, 12, 36, 39
SHA = "8e1ee4c48e"                                                    # cpapp-b.bin of ZV-E1 2.02 (prefix; the full hash goes in the design)
T = {"ids": 0xDCC524, "colmap": 0xDCDD00, "rx": 0xDCCD10, "rx2": 0xDCD634, "d": 0xDCD8A4, "tim": 0xDCCEE4, "tim_b": 0xDCCEE4 + 0x3A8,
     "win": 0xEB6292, "st1": 0xEB685C, "lc": 0xEB6E26, "crop": 0xDCC5C0, "rl": 0xEB7048, "geo": 0xD7BF68 + 12 * 12}
ROW = {"colmap": 8, "rx": 12, "rx2": 16, "d": 28, "tim": 24, "tim_b": 24, "win": 38, "st1": 38, "lc": 14, "crop": 20, "rl": 16}
UNITS = {"59.94 system": 1501500, "50 system": 1500000}
TIMING = {"tim": (313, 4788, 57, 34, 287, 5220, 87, 56, "59.94 system"), "tim_b": (313, 4780, 239, 193, 268, 5580, 93, 76, "50 system")}
RECS = {"L": 0xD35F14, "R": 0xD36ACC}
STILL = {"L": 0xD4264C, "R": 0xD43204}
PACKER = {"CamArc": 0x267F48, "CamNrs": 0x7885CC, "CamSig": 0x7904E0, "CamLrc": 0x788588, "Dev (first packer)": 0x787AE8,
          "Dev (second packer)": 0x78796E, G.BEYOND: 0x787AE8}
LOG, FIT = 0xB268AC, 0x790040
# v1 (a guess): the A7S III's run-time bytes of the 0x15c record, moved to the 0x170 layout (a 4-byte field at +0x1c, as the A7C II). Two of them,
# +0x129 and +0x15e, are calculator output on this body: v1 left them stock, so its record held +0x128 = 0x47b1 (stock 0x47ea, calculated 0x45b1)
# and +0x15e = 47 (calculated 49).
RUNTIME_V1 = {o if o < 0x1C else o + 4 for o in V3.RUNTIME}
# v2: what a ZV-E1 showed (first test, 2026-11-23: three dumps, before the apply, after it and after the restart): only +0x11a/+0x11b of the 0x8c0
# record differ from the calculator's (0x80, 0x80 on the camera; 0 in the emulation). Neither is a byte the design changes.
RUNTIME = {0x11A, 0x11B}


def configure():
    V.BUILD, V.STOCK, V.STILL, V.PACKER, V.LOG, V.FIT = BUILD, RECS, STILL, PACKER, LOG, FIT


def trow(h, v, p, e):
    return struct.pack("<3I", h, v, 1 | p << 8 | e << 16) * 2


def cells(img):
    """[(label, address, old bytes, new bytes, note)] for drive mode index 12. Every old value is checked against the image."""
    at = lambda t, i=INDEX: T[t] + ROW[t] * i
    rd = lambda a, n: img[a - BASE:a - BASE + n]
    ids = struct.unpack_from("<%dI" % NMODES, img, T["ids"] - BASE)
    assert ids[INDEX] == MODE and ids[SRC] == 0xE011 and NMODES == 39
    out = []

    def cell(label, addr, new, note, old=None):
        cur = rd(addr, len(new))
        assert old is None or cur == old, (label, cur.hex(), old.hex())
        if cur != new:
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
    cell("C", at("colmap"), struct.pack("<I", 1), "column map: register matrix column 11 (the 16:9 band) -> 1 (full height), as 0xe011", struct.pack("<I", 11))
    assert rd(at("rx"), 8) == struct.pack("<2I", 6, 3) and rd(at("rx", SRC), 8) == struct.pack("<2I", 0, 2)
    as_source("R1", "rx", 0, 12, "receiver type: 6, 3 -> 0, 2, as 0xe011 (12-bit link)")
    as_source("R2", "rx2", 0, 16, "receiver type, second table: 6, 3 -> 0, 2")
    as_source("D", "d", 4, 6, "0xdcd8a4 +4: 478 -> 484, the value of the modes on sensor mode 0x01 (meaning not known; as ogsq_s3_v5)")
    for t, (h, v, p, e, h0, v0, p0, e0, system) in TIMING.items():
        assert h * v + (v // p) * e == UNITS[system] and v % p == 0 and v % 4 == 0 and h0 * v0 + (v0 // p0) * e0 == UNITS[system]
        assert e < p and v >= 122 + 22 + 6 + 8 + 2832 + 8
        cell(f"T.{t}", at(t), trow(h, v, p, e), f"timing row, {system}: {h0}, {v0}, P {p0}, E {e0} -> {h}, {v}, P {p}, E {e} ({36e6 / UNITS[system]:.4f} fps)",
             trow(h0, v0, p0, e0))
    as_source("W", "win", 0, 38, "stream-0 window row: 0xe011's (top margins 38, 6 -> 122, 22; height 2392 -> 2832)")
    as_source("A", "st1", 0, 38, "aux stream-1 row: 0xe011's")
    as_source("LC", "lc", 0, 14, "LC row: 0xe011's (V offset 220 -> 0, field 6 235 -> 37)")
    as_source("CR", "crop", 0, 20, "crop row: 0xe011's (V offset 220 -> 0, last field 2 -> 0)")
    assert rd(T["geo"], 12) == bytes.fromhex("c008000000000000a201dc00")
    cell("G", T["geo"] + 10, struct.pack("<H", 0), "geometry row of 0x8c0: V offset 220 -> 0 (field +8 = 418, ZV-E1 only, left alone)", struct.pack("<H", 220))
    assert struct.unpack_from("<8H", img, at("rl") - BASE) == (16, 1, 2, 8, 1000, 0, 618, 618)
    cell("L", at("rl") + 12, struct.pack("<2H", 728, 728), "read-out table: row fields 618 -> 728 (2832 / 4 + 20); this body has no frame-length fields")
    spans = sorted((a, len(n)) for _, a, _, n, _ in out)
    assert all(a + n <= b for (a, n), (b, _) in zip(spans, spans[1:])), "cells overlap"
    return out


def link12(rec):
    """ogsq_s3_v5's change: the five link-format words and +0x274 set for a 12-bit link. Returns the rows changed."""
    w = lambda off: struct.unpack_from("<I", rec, off)[0]
    rows = []
    for off, (v10, v12) in sorted(LF.LINK_WORDS.items()):
        assert w(off) == v10, f"+{off:#x} is not the 10-bit value"
        rows.append((off, v10, v12))
        struct.pack_into("<I", rec, off, v12)
    want = (w(0x278) & 0xFFFF) + LF.WIDTH_EXTRA[False]
    assert w(0x274) == (w(0x278) & 0xFFFF) + LF.WIDTH_EXTRA[True]
    rows.append((0x274, w(0x274), want))
    struct.pack_into("<I", rec, 0x274, want)
    return rows


def main():
    v = sys.argv[1:]
    name = v[v.index("--name") + 1] if "--name" in v else "ogsq_zv_v2"
    runtime = RUNTIME_V1 if name == "ogsq_zv_v1" else RUNTIME
    configure()
    img = V.image()
    sha = hashlib.sha256(img).hexdigest()
    assert sha.startswith(SHA), sha
    m = V.Model(img)
    rep = m.check()
    for h in "LR":
        assert not rep[h]["off_rule"] and not rep[h]["zero_on_this_build"] and not any(rep[h]["packer_words_not_reproduced_on_stock"].values()), rep[h]
    rec, _words = m.build(2848, 0)
    links = {h: link12(rec[h]) for h in "LR"}
    cs = cells(img)
    stock, log0 = emu_drvparam.records(BUILD)
    new, log1 = emu_drvparam.records(BUILD, [(a, n) for _, a, _, n, _ in cs])
    assert not log0 and not log1, (log0, log1)
    (i0, s_rec, e0), (i1, n_rec, e1) = stock[MODE], new[MODE]
    assert i0 == i1 == INDEX and not e0 and not e1 and len(s_rec) == 0x170 and s_rec[4:8] == b"\x01\x01\x01\x01"
    others = [hex(x) for x in stock if x != MODE and stock[x][1] != new[x][1]]
    assert not others, f"the cells change other modes' records: {others}"
    d_rec = bytearray(n_rec)
    d_rec[6], d_rec[7] = 16, 19
    diff = [o for o in range(len(s_rec)) if s_rec[o] != d_rec[o]]
    held = [o for o in diff if o in runtime]
    for o in held:
        d_rec[o] = s_rec[o]
    diff = [o for o in diff if o not in runtime]
    src = stock[0xE011][1]
    vs_src = [o for o in range(len(s_rec)) if d_rec[o] != src[o]]
    g = lambda h, o: struct.unpack_from("<H", rec[h], o)[0]
    lrc = {h: {"input": [g(h, 0x160), g(h, 0xE)], "output": [g(h, 0x178), g(h, 0x17A)], "crop_rows": [g(h, 0x13A), g(h, 0x13E)],
               "final": [g(h, 0x194), g(h, 0x196)]} for h in "LR"}
    patches = [{"kind": "S", "addr": hex(a), "old": o.hex(), "new": n.hex(), "note": f"{lab} {note}", "where": "file"} for lab, a, o, n, note in cs]
    for h, nm in (("L", "left"), ("R", "right")):
        old = img[RECS[h] - BASE:RECS[h] - BASE + V.SIZE]
        n = sum(old[o:o + 2] != rec[h][o:o + 2] for o in range(0, V.SIZE, 2))
        patches.append({"kind": "R", "addr": hex(RECS[h]), "old": old.hex(), "new": bytes(rec[h]).hex(), "where": "file",
                        "note": f"0x8c0 {nm} record (shared with 0x820): first-stage window of 2848 rows from active row 0 of the full-height frame, "
                                f"squeezed by Lrc into the stock half picture, link words for a 12-bit link; {n} fields differ from stock"})
    out = {"design": name, "build": BUILD, "camera": "ZV-E1, firmware 2.02",
           "title": "Full height in drive mode 0x8c0 through the sensor's full-height mode (matrix column 1, as 0xe011), first-stage window of 2848 rows "
                    "squeezed by Lrc into the stock picture, picture records set for the 12-bit link (port of the A7S III's ogsq_s3_v5)",
           "status": "built from the firmware files and emulated in parts; never run on a ZV-E1",
           "artifact": "cpapp-b.bin", "artifact_sha256": sha, "generated_by": "build/build_og_zv.py",
           "ported_from": {"design": "ogsq_s3_v5", "build": "a7s3_501"},
           "mode_id": hex(MODE), "mode_index": INDEX, "sensor_mode_taken_from": f"0xe011 (index {SRC})",
           "records_base": hex(emu_drvparam.CONSTS[BUILD]["fields"][0x10]), "record_size": 0x170,
           "timing": {k: {"hmax": t[0], "vmax": t[1], "p": t[2], "e": t[3], "units": UNITS[t[8]], "fps": round(36e6 / UNITS[t[8]], 6), "system": t[8]} for k, t in TIMING.items()},
           "summary": {"sites": len(patches), "bytes": sum(len(p["new"]) // 2 for p in patches), "sensor_cells": len(cs), "records": 2},
           "lrc": lrc, "link_words": {h: [[hex(o), hex(a), hex(b)] for o, a, b in rows] for h, rows in links.items()}, "check": rep, "patches": patches,
           "stored_record": {"address": hex(emu_drvparam.CONSTS[BUILD]["fields"][0x10] + INDEX * 0x170), "stock": s_rec.hex(), "design": bytes(d_rec).hex(),
                             "offsets_that_differ": [hex(o) for o in diff], "run_time_offsets_left_alone": [hex(o) for o in held],
                             "bytes_differing_from_0xe011_record": len(vs_src)},
           "guesses": ["everything ogsq_s3_v5 guessed (0xdcd8a4 +4 = 484, the timing rows' P and E, the class byte kept at 0)",
                       "the geometry row's ZV-E1-only field +8 (418) does not need to change for full height",
                       "the A7S III's run-time bytes of the stored record, moved by 4 past +0x1c, are this body's run-time bytes",
                       "receiver type 6 (the ZV-E1's 4K rows; 5 on the A7S III) behaves like 5 when replaced by 0, 2"],
           "not_shown": ["anything on a ZV-E1", "the raw write buffer's room for a full-height frame on this body",
                         "the live-view fault of the A7S III (glitchy live view when movie mode is entered from stills) on this body"]}
    if name != "ogsq_zv_v1":
        out["status"] = "built from the firmware files and emulated in parts; v1 was run on a ZV-E1 (2026-11-23): every site applied, then a restart on entering movie mode"
        out["requires"] = {"dmmwb_zv_v1": "applied first: without it the 2848-row first stage does not fit the raw write buffer (4288 x 2408 on this body) and "
                                          "the camera core never starts it; that restarted the camera in the v1 test (build/build_dmm_zv.py)"}
        out["changes_from_v1"] = ["stored record: +0x129 and +0x15e hold the calculated values (v1 kept them stock: +0x128 read 0x47b1, half stock, half new)",
                                  "the run-time bytes left alone are the camera's own, +0x11a/+0x11b (seen in three ZV-E1 dumps), which the design does not change"]
        out["guesses"] = [g for g in out["guesses"] if "run-time bytes" not in g]
        out["not_shown"] = ["a ZV-E1 picture in movie mode with this design (v1 restarted the camera before any picture: raw write buffer)",
                            "the live-view fault of the A7S III (glitchy live view when movie mode is entered from stills) on this body"]
    dst = ROOT / "modding" / "designs" / f"{name}.json"
    dst.write_text(json.dumps(out, indent=1) + "\n", encoding="utf8", newline="\n")
    print(f"{name}: {len(cs)} sensor cells + 2 records = {len(patches)} sites, {out['summary']['bytes']} bytes")
    for lab, a, o, n, note in cs:
        print(f"  {lab:10} {a:#x} {o.hex()} -> {n.hex()}")
    print("lrc", json.dumps(lrc))
    print(f"stored record: {len(diff)} bytes differ from stock at {[hex(o) for o in diff]}; run-time left alone {[hex(o) for o in held]}; "
          f"differs from 0xe011's record in {len(vs_src)} bytes")
    print("wrote", dst)


if __name__ == "__main__":
    main()
