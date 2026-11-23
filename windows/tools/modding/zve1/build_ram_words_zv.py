"""ZV-E1 2.02 (zve1_202) versions of two coprocessor RAM-word designs (ZV-E1 port, 2026-11-24; modding/ZVE1_PORT_PART_A.md).

  C:/Python313/python.exe -B build/build_ram_words_zv.py         writes outsz2560_zv_v1 and lcdfill_zv_v2 to modding/designs/

The ZV-E1 is the A7C II's platform generation with the A7S III's sensor. Each A7 IV design is translated site by site and guard by
guard to the ZV-E1's addresses, and every old byte and every guard byte is checked again on the ZV-E1 side:
  - outsz2560_v1 -> outsz2560_zv_v1. The ZV-E1's movie size-table set-up 0x4aadd8 (match_seed / match_thumb from the A7C II's 0x4b7354,
    135 votes, exact masked match; build/emu_size_table.py zve1_202) fills base 0x19964c4 + 0x50 with exactly the A7C II's table (one
    class more than the A7 IV: 8192x4320 is class 1). The 3840x2160 entries are 0x1996554 / 0x199655c; the reader's UHD case
    (0x4c7adc, matched from the A7C II's 0x4d436c, 64 votes) loads base+0x98 = 0x199655c, as the A7C II's loads 0x1a531c8.
  - lcdfill_v2 -> lcdfill_zv_v2. The VDF fit-mode function and its tables are byte-identical to the A7 IV's (0x1e4b78 -> 0x1f5c34,
    0x94 bytes; the only place in the image). Fit word for a 16:9 picture on panel code 1 (3:2): 0x1f5c88.
    Frame widgets: the ZV-E1 has TWO rectangle tables, not three. cpActAfWindow's check (0x128644, aligned with the A7C II's 0x128558)
    reads 0xe9b3e0 and cpActTrackingFrame's (0x1295ca, aligned with 0x129992) reads 0xe9b458; both tables are byte-identical to the A7 IV's
    0xd7b560. cpActAfWindowRemoteSend does not exist in this firmware (no name string; the A7C II's 0x128e4e has no counterpart), so its
    table and its two sites are left out: 5 sites, not 7. Both checks index the table as the A7C II's (row = panel x 5 + aspect index,
    aspect index table 0xcab860 = the A7C II's (2, 1, 0, 3, 0, 3, 0, 4)).
Not read from the firmware: that the ZV-E1's rear panel reports panel code 1 (3:2). Sony's specification gives a 3.0-type 1,036,800-dot
screen (720 x 480 x 3, a 3:2 panel, as the A7 IV's and A7C II's); the run-time byte that decides it is the rear output's panel type at
0x1a71840 (record 0x1a71824 + 0x1c, ported from the A7S III's 0x14b9600: 6 references, 40-84 votes each). A dump can read it.
Design only: nothing is written to a firmware file, nothing is sent to a camera.
"""
import hashlib
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "build"))
import locate_file  # noqa: E402
import emu_size_table  # noqa: E402

B, BUILD = 0x108000, "zve1_202"
IMG = locate_file.locate(BUILD, "cpapp-b.bin").read_bytes()
IMG_A = locate_file.locate("a7iv_602", "cpapp-b.bin").read_bytes()
SHA = hashlib.sha256(IMG).hexdigest()
FIT_A, FIT_Z, FIT_LEN = 0x1E4B78, 0x1F5C34, 0x94                    # fit-mode function and its tables
FRAMES_A, FRAMES_Z = (0xD7B560, 0xD7B5D8, 0xD7B650), (0xE9B3E0, None, 0xE9B458)    # AfWindow, AfWindowRemoteSend, TrackingFrame
SIZE_A, SIZE_Z = 0x143C784 - 0x50 + 0x80, None                      # filled below from the emulation


def known_size_table():
    t, rows, _ = emu_size_table.table(BUILD)
    assert t == 0x1996514 and rows[8] == (3840, 2160, 0x43E) and rows[9] == (3840, 2160, 0x2D9), (hex(t), rows[8:10])
    ta, rows_a, _ = emu_size_table.table("a7c2_201")
    assert rows == rows_a, "the ZV-E1's size table is not the A7C II's"
    known = {}
    for k, (w, h, mid) in enumerate(rows):
        for j, x in enumerate(struct.pack("<2HI", w, h, mid)):
            known[t + 8 * k + j] = x
    return t, known


def tr_lcd(a, n):
    """A7 IV address of lcdfill_v2 -> ZV-E1 address, or None for the table the ZV-E1 does not have."""
    if FIT_A <= a and a + n <= FIT_A + FIT_LEN:
        return a - FIT_A + FIT_Z
    for fa, fz in zip(FRAMES_A, FRAMES_Z):
        if fa <= a and a + n <= fa + 0x78:
            return None if fz is None else a - fa + fz
    raise SystemExit(f"no ZV-E1 counterpart for {a:#x}")


def main():
    assert IMG[FIT_Z - B:FIT_Z - B + FIT_LEN] == IMG_A[FIT_A - B:FIT_A - B + FIT_LEN], "fit function and tables are not the A7 IV's"
    for fa, fz in zip(FRAMES_A, FRAMES_Z):
        if fz is not None:
            assert IMG[fz - B:fz - B + 0x78] == IMG_A[fa - B:fa - B + 0x78], f"frame table {fz:#x} is not the A7 IV's {fa:#x}"
    assert b"cpActAfWindowRemoteSend" not in IMG
    t, known = known_size_table()
    des = ROOT / "modding" / "designs"
    # ---- outsz2560_zv_v1
    src = json.loads((des / "outsz2560_v1.json").read_text(encoding="utf8"))
    sh = (t + 8 * 9) - 0x143C7BC                                         # A7 IV class 3 entry 1 -> ZV-E1 class 4 entry 1
    sites, guards = [], []
    for x in src["sites"]:
        a, old, new = int(x["ram_address"], 16), bytes.fromhex(x["old"]), bytes.fromhex(x["new"])
        z = a + sh
        assert bytes(known[z + j] for j in range(4)) == old
        sites.append({"ram_address": hex(z), "old": old.hex(), "new": new.hex(), "note": x["note"].replace("size class 3", "size class 4 (class 3 on the A7 IV)") + f" [A7 IV {a:#x}]"})
    for g in src["guards"]:
        a, b = int(g["ram_address"], 16), bytes.fromhex(g["bytes"])
        z = a + sh
        assert bytes(known[z + j] for j in range(len(b))) == b, (hex(z), b.hex())
        guards.append({"ram_address": hex(z), "bytes": b.hex(), "note": g["note"] + f" [A7 IV {a:#x}]"})
    out = {"design": "outsz2560_zv_v1", "build": BUILD, "title": src["title"] + " (ZV-E1 2.02 port)", "kind": "ram_words",
           "artifact": src["artifact"], "generated_by": "build/build_ram_words_zv.py", "ported_from": {"design": "outsz2560_v1", "build": "a7iv_602"},
           "table": src["table"] + " [A7 IV addresses; ZV-E1: set-up 0x4aadd8, size table 0x19964c4+0x50 (the A7C II's contents), UHD reader case 0x4c7adc loads base+0x98]",
           "summary": src["summary"], "sites": sites, "guards": guards,
           "checked_against": ["build/emu_size_table.py zve1_202 (the ZV-E1's set-up run alone): the same 16 entries as the A7C II's",
                               "the reader 0x4c7adc aligned with the A7C II's 0x4d436c (build/diff_consts.py): case 3 loads base+0x98"],
           "not_shown": ["anything on a camera", "the output records' format code on this camera (2 on the A7 IV)"]}
    write(des, out)
    # ---- lcdfill_zv_v2
    src = json.loads((des / "lcdfill_v2.json").read_text(encoding="utf8"))
    sites, guards, dropped = [], [], []
    for x in src["sites"]:
        a, old, new = int(x["ram_address"], 16), bytes.fromhex(x["old"]), bytes.fromhex(x["new"])
        z = tr_lcd(a, 4)
        if z is None:
            dropped.append(hex(a))
            continue
        assert IMG[z - B:z - B + 4] == old, hex(z)
        sites.append({"ram_address": hex(z), "old": old.hex(), "new": new.hex(), "note": x["note"] + f" [A7 IV {a:#x}]"})
    for g in src["guards"]:
        a, b = int(g["ram_address"], 16), bytes.fromhex(g["bytes"])
        z = tr_lcd(a, len(b))
        if z is None:
            dropped.append(hex(a))
            continue
        assert IMG[z - B:z - B + len(b)] == b, hex(z)
        guards.append({"ram_address": hex(z), "bytes": b.hex(), "note": g["note"] + f" [A7 IV {a:#x}]"})
    assert len(sites) == 5 and len(guards) == 9 and len(dropped) == 4, (len(sites), len(guards), dropped)
    sa = [int(x["ram_address"], 16) for x in sites]
    for g in guards:
        ga, gn = int(g["ram_address"], 16), len(g["bytes"]) // 2
        assert not any(ga < v + 4 and v < ga + gn for v in sa), "a guard overlaps a site"
    summ = dict(src["summary"], sites=5, bytes=20, goes_with=["the open-gate state", "the ZV-E1 preview-key routine"])
    out = {"design": "lcdfill_zv_v2", "build": BUILD, "title": src["title"] + " (ZV-E1 2.02 port)", "kind": "ram_words",
           "artifact": src["artifact"], "artifact_sha256": SHA, "generated_by": "build/build_ram_words_zv.py",
           "ported_from": {"design": "lcdfill_v2", "build": "a7iv_602"},
           "table": src["table"] + " [A7 IV addresses; ZV-E1: fit table 0x1f5c84 (function 0x1f5c34), frame tables 0xe9b3e0 (AfWindow), 0xe9b458 (TrackingFrame)]",
           "summary": summ, "sites": sites, "guards": guards,
           "left_out": {"a7iv_addresses": dropped, "why": "cpActAfWindowRemoteSend and its rectangle table (A7 IV 0xd7b5d8) do not exist in the ZV-E1 2.02 firmware"},
           "checked_against": ["cpapp-b.bin 2.02: fit function and tables byte-identical to the A7 IV's (0x1e4b78 -> 0x1f5c34), both frame tables byte-identical to 0xd7b560",
                               "the two checks that read the frame tables aligned with the A7C II's (build/diff_consts.py): same row computation and aspect index table"],
           "not_shown": ["that the ZV-E1's rear panel is panel code 1 (3:2): Sony's specification (1,036,800 dots = 720 x 480); the run-time panel type byte is 0x1a71840",
                         "that the frame widgets use row 1 on this body (carried over from the A7 IV)", "anything on a camera"]}
    write(des, out)


def write(des, out):
    name = out["design"]
    (des / f"{name}.json").write_text(json.dumps(out, indent=1) + "\n", encoding="utf8", newline="\n")
    (des / f"{name}_pokes_ram.txt").write_text("".join(f"{x['ram_address']} {x['new']}\n" for x in out["sites"]), encoding="utf8", newline="\n")
    print(name, [(x["ram_address"], x["old"], x["new"]) for x in out["sites"]], len(out["guards"]), "guards")


if __name__ == "__main__":
    main()
