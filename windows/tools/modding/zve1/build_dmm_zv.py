"""Build the ZV-E1 2.02 memory-only change `dmmwb_zv_v1`: the movie raw write buffer (memory id 0x43e) large enough for a full-height frame.

  C:/Python313/python.exe -B build/build_dmm_zv.py [--name dmmwb_zv_v1]

Why (first camera test of ogsq_zv_v1, 2026-11-23): movie mode 0x8c0 with the full-height sensor cells restarted the camera. The coprocessor's
kept kprint log holds the forced exception of CAM_VD_SEQUENCE at 0x4b2d86 ("FW: S-Ele Refresh ng force exception": Dev still busy at its sync
point for 11 frames), the A7 IV's F525/F667 signature. The cause there was the raw write buffer (F673), and it is here:

  - In movie mode the camera core writes each raw frame into a unit of memory id 0x43e (DMM key 0x57f; the dump's movie size table names id
    0x43e for 3840x2160). Its port set-up 0x2613a8 (= A7 IV 0x247898) refuses a frame larger than the unit with "CamCore: AIF%d out[0x%x] >
    memsize[0x%x]" (0x261472) and reports no error, so the first stage never starts and Dev waits.
  - On the ZV-E1 that unit is 10,325,504 bytes = 4288 x 2408: exactly the stock 4K first stage (2392 + 16 rows). The full-height stage is
    2832 + 16 = 2848 rows: 4288 x 2848 = 12,212,224 bytes do not fit.
  - The A7S III, where ogsq_s3_v5 works, gives the same unit 26,214,400 bytes in the same layout: one unit alone in group 0x87 of the same
    28,311,552-byte parent (key 0x38). On the ZV-E1 the group is 0x89 (limit 7 instead of 6), and the unit is the only thing that differs.

The change: the size field of that one unit record in the coprocessor's RAM copy of DmmCfg.bin becomes the A7S III's 26,214,400. Unlike
the A7 IV (dmmwb4688_v1, four words) no second layout needs steering: the group has room in its parent.

Checked in the ZV-E1's own allocator code (build/emu_dmm_server.py --build zve1_202): see the design's "checked_in_the_firmware_allocator".
Nothing here writes a firmware file; a cold boot reloads the tables from /cp/DmmCfg.bin. Never run on a ZV-E1.
"""
import json
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "build"))
import emu_dmm_server as E  # noqa: E402
import parse_dmmcfg as P  # noqa: E402

BUILD, KEY, GROUP, PARENT, MEM_ID = "zve1_202", 0x57F, 0x89, 0x38, 0x43E
STOCK, NEW, LIMIT = 10325504, 26214400, 7
PITCH, STOCK_ROWS, FULL_ROWS = 4288, 2408, 2848          # 4240 columns padded to 64 bytes; rows = window height + 16
CHECK_FN, CHECK_MSG = 0x2613A8, 0x261472                  # the raw port set-up and its refusal (cpapp-b.bin 2.02)


def main():
    v = sys.argv[1:]
    name = v[v.index("--name") + 1] if "--name" in v else "dmmwb_zv_v1"
    E.use_build(BUILD)
    cfg = P.Config(P.find_file(BUILD), BUILD)
    assert STOCK == PITCH * STOCK_ROWS and PITCH * FULL_ROWS <= NEW and NEW % 128 == 0
    units = cfg.units_by_key[KEY]
    assert len(units) == 1 and units[0]["group"]["gid"] == GROUP and units[0]["size"] == STOCK and cfg.ids_by_key[KEY] == [MEM_ID]
    u = units[0]
    g = u["group"]
    assert g["parent"] == PARENT and [x["key"] for x in g["units"]] == [KEY] and set(g["limits"]) == {LIMIT}
    parent = min(cfg.parent_sizes(PARENT))
    assert parent == 28311552 and NEW <= parent
    rec = cfg.ram("unit_records", u["seq"] * 0x14)
    site = {"ram_address": hex(rec + 12), "what": f"size of the key {KEY:#x} record of group {GROUP:#x} (memory id {MEM_ID:#x}, the movie raw write buffer)",
            "file_offset_of_the_same_field": hex(u["at"] + 12), "old": struct.pack("<I", STOCK).hex(), "new": struct.pack("<I", NEW).hex(),
            "old_value": STOCK, "new_value": NEW}

    def run(plan, apply_first=True):
        s = E.Server(cfg.data, cfg)
        assert s.init() == 0 and s.cur == len(cfg.data) and not s.fatal
        assert s.u32(rec + 12) == STOCK, "the RAM copy is not where parse_dmmcfg.RAM says"
        if apply_first:
            s.set_size(KEY, GROUP, NEW)
            assert bytes(s.uc.mem_read(rec + 12, 4)).hex() == site["new"]
        out = []
        for step in plan:
            if step == "apply":
                s.set_size(KEY, GROUP, NEW)
                out.append({"step": "apply"})
            elif step[0] == "open":
                out.append(s.open(step[1]))
            else:
                out.append(s.free(step[1]))
        return s, out

    # 1. the change in place before the first open: the layout's limit of buffers, the parent's other users, everything frees
    plan = [("open", MEM_ID)] * (LIMIT + 1) + [("open", 0x4B7), ("open", 0x4B8)] + [("free", n) for n in range(LIMIT)] + [("free", LIMIT + 1), ("free", LIMIT + 2)]
    s, out = run(plan)
    opens = [o for o in out if o["step"] == "open"]
    wb = opens[:LIMIT]
    assert all(o["ok"] and [x["size"] for x in o["extents"]] == [NEW] for o in wb), "an open of 0x43e did not return the new size"
    assert not opens[LIMIT]["ok"], f"an open beyond the layout's limit of {LIMIT} was expected to be refused"
    assert opens[LIMIT + 1]["ok"] and opens[LIMIT + 1]["extents"][0]["size"] == 3317760 and opens[LIMIT + 2]["ok"] and opens[LIMIT + 2]["extents"][0]["size"] == 13271040
    spans = sorted((int(x["address"], 16), int(x["address"], 16) + x["size"]) for o in opens if o["ok"] for x in o["extents"])
    assert all(a[1] <= b[0] for a, b in zip(spans, spans[1:])), "opened units overlap"
    bases = sorted(cfg.bases(PARENT))
    assert all(any(b <= lo and hi <= b + parent for b in bases) for lo, hi in spans), "a unit lies outside its parent"
    assert all(o["ok"] for o in out if o["step"] == "free") and not s.fatal and not [o for o in s.objects() if o["in_use"]]
    # 2. stock control: the same plan without the change hands out the same places at the stock size
    s0, out0 = run(plan, apply_first=False)
    opens0 = [o for o in out0 if o["step"] == "open"]
    assert [o["extents"][0]["address"] for o in opens0[:LIMIT]] == [o["extents"][0]["address"] for o in wb], "the change moves the buffers"
    assert all(o["extents"][0]["size"] == STOCK for o in opens0[:LIMIT]) and not opens0[LIMIT]["ok"]
    # 3. written while a buffer of the stock division is open: that one keeps its size; once it is freed the next opens get the new size
    s2, out2 = run([("open", MEM_ID), "apply", ("open", MEM_ID), ("free", 0), ("open", MEM_ID)], apply_first=False)
    o2 = [o for o in out2 if o.get("step") == "open"]
    busy = {"open_before": o2[0]["extents"], "open_while_it_is_in_use": o2[1]["extents"], "open_after_it_was_freed": o2[2]["extents"]}
    assert o2[0]["extents"][0]["size"] == STOCK
    design = {"design": name, "build": BUILD, "camera": "ZV-E1, firmware 2.02",
              "title": f"Memory-only DMM change: the movie raw write buffer (memory id {MEM_ID:#x}) grows from {PITCH} x {STOCK_ROWS} to the A7S III's "
                       f"{NEW:,} bytes, room for the {FULL_ROWS}-row full-height first stage",
              "artifact": "coprocessor RAM (the DMM server's copy of /cp/DmmCfg.bin); no file is changed", "generated_by": "build/build_dmm_zv.py",
              "why": {"camera": "first test of ogsq_zv_v1 (2026-11-23): restart on entering movie mode; kept kprint: CAM_VD_SEQUENCE data abort at 0x4b2d86, "
                                "the deliberate write to 0 after 'FW: S-Ele Refresh ng force exception' (Dev busy at its sync point for 11 frames)",
                      "code": f"raw port set-up {CHECK_FN:#x} refuses a frame larger than its unit ({CHECK_MSG:#x}: 'CamCore: AIF%d out[0x%x] > memsize[0x%x]'), "
                              "required = ((step + 1) * (rows - 1) + 1) * pitch",
                      "sizes": {"stock_unit": STOCK, "stock_stage": f"{PITCH} x {STOCK_ROWS}", "full_height_stage": f"{PITCH} x {FULL_ROWS} = {PITCH * FULL_ROWS:,}",
                                "a7s3_501_unit": NEW, "a7iv_602_unit": 27864320}},
              "summary": {"sites": 1, "bytes": 4, "unit_size": NEW, "stock_unit_size": STOCK, "group": hex(GROUP), "parent_key": hex(PARENT), "parent_size": parent,
                          "left_free_in_the_parent": parent - NEW, "layout_limit": LIMIT, "rows_at_4288": NEW // PITCH,
                          "cache_lines_64": [hex((rec + 12) & ~63)], "record": hex(rec)},
              "precondition": "no unit object of key 0x57f exists in a division still in force when the word is written (the helper checks the DMM server's "
                              "unit objects and writes nothing otherwise): with the camera on stills after a cold boot, no movie buffer is open",
              "restore": "write the old word back under the same condition, or cold boot (the tables are rebuilt from /cp/DmmCfg.bin)",
              "checked_in_the_firmware_allocator": {
                  "tool": "build/emu_dmm_server.py --build zve1_202 (the ZV-E1's own DMM server code, alone; see its header for what is made up)",
                  "applied_before_any_open": {"opens_of_0x43e": [o["extents"] for o in wb], "open_beyond_the_limit": opens[LIMIT]["result"],
                                              "open_0x4b7": opens[LIMIT + 1]["extents"], "open_0x4b8": opens[LIMIT + 2]["extents"],
                                              "all_inside_a_parent_and_disjoint": True, "same_places_as_stock": True, "all_freed": True},
                  "written_while_a_stock_buffer_is_open": busy,
                  "stock_control": [o["extents"] for o in opens0[:LIMIT]]},
              "not_shown": ["that the image hardware takes the full-height stage once the buffer is large enough (the A7S III does, with this size)",
                            "what the camera has open when the word is written (the helper checks it and writes nothing if a movie buffer exists)"],
              "sites": [site]}
    d = ROOT / "modding/designs"
    (d / f"{name}.json").write_text(json.dumps(design, indent=1) + "\n", encoding="utf8", newline="\n")
    (d / f"{name}_pokes_ram.txt").write_text(f"{site['ram_address']} {site['new']}\n", encoding="ascii", newline="\n")
    print(f"{name}: 1 site {site['ram_address']} {site['old']} -> {site['new']} ({STOCK:,} -> {NEW:,}); record {rec:#x}; parent left {parent - NEW:,}")
    print("  opens with the change:", [o["extents"][0]["address"] for o in wb], "beyond the limit:", opens[LIMIT]["result"])
    print("  written while a stock buffer is open:", json.dumps(busy))


if __name__ == "__main__":
    main()
