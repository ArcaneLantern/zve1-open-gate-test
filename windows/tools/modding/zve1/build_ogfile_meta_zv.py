"""Build the ZV-E1 2.02 encoder design `ogfile2560_hs_s_zv_v2`: `ogfile2560_hs_s_zv_v1` plus the MP4 header height (2026-11-24).

  python -I -B build_ogfile_meta_zv.py            (reads modding/designs/ogfile2560_hs_s_zv_v1.json and the extracted 2.02 libmpr.so)

The same change as the A7 IV's ogfile2560_hs_s_v2 (`build_ogfile.py --meta`): v1 plus two instructions of libmpr.so, in the MP4 writer's
request set-up (0x207d14 on this body, 0x222b18 on the A7 IV), where width, height and sample-entry type are written per case:

  0x207d8c  the 3840-wide AVC case (sample entry avc1): mov w6,#0x870 (2160) -> mov w6,#0xa00 (2560)   (A7 IV 0x222b90)
  0x207dd8  the 3840-wide HEVC case (sample entry hvc1): mov w6,#0x870 (2160) -> mov w6,#0xa00 (2560)  (A7 IV 0x222bdc)

v1 already lists both as its "optional_sites"; v2 makes them sites. The A7 IV sites lie 0x1ae04 higher; the two instructions before and the
two after each site are the same bytes on both bodies. `06 0e 81 52` occurs three times in this libmpr.so: the third, 0x207f3c, is the
4096-wide case (mov w7,#0x1000 follows it) and is not touched. With v2 the file's tkhd, its stsd entry and Sony's PROF box say 3840x2560;
Sony's XML (the M01.XML beside the file and the one inside it) still says 3840x2160 16:9.

Design only: nothing is written to a firmware file, nothing is sent to a camera.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EX = ROOT / "work/extracted/zve1_202/0700_part_image/dev"
DES = ROOT / "modding/designs"
STOCK, NEW = bytes.fromhex("060e8152"), bytes.fromhex("06408152")      # mov w6,#0x870 / mov w6,#0xa00
W3840, W4096 = bytes.fromhex("07e08152"), bytes.fromhex("07008252")    # mov w7,#0xf00 / mov w7,#0x1000
SITES = ((0x207D8C, "XAVC S 4K (AVC, sample entry avc1)", 0x61766331, 0x222B90),
         (0x207DD8, "XAVC HS 4K (HEVC, sample entry hvc1)", 0x68766331, 0x222BDC))
LOOKALIKE = 0x207F3C
NEIGHBOURS = {0x207D8C: "4401805245008052" + "07e08152f7ffff17", 0x207DD8: "e503022a44018052" + "07e0815228668c52"}   # = the A7 IV's guards


def sample_entry(lm, off):
    """The sample-entry type the case loads into w8 (mov w8,#lo ; movk w8,#hi,lsl #16) after the site at `off`, following a plain branch
    (the AVC case branches back to the shared code at 0x207d70)."""
    k = off + 8
    for _ in range(8):
        a, b = int.from_bytes(lm[k:k + 4], "little"), int.from_bytes(lm[k + 4:k + 8], "little")
        if a & 0xFC000000 == 0x14000000:                                  # b <label>
            k += ((a & 0x3FFFFFF) ^ 0x2000000) - 0x2000000 << 2
            continue
        if a & 0xFFE0001F == 0x52800008 and b & 0xFFE0001F == 0x72A00008:
            return (a >> 5 & 0xFFFF) | (b >> 5 & 0xFFFF) << 16
        return None
    return None


def main():
    v1 = json.loads((DES / "ogfile2560_hs_s_zv_v1.json").read_text(encoding="utf8"))
    lm = (EX / "nflasha15/lib/libmpr.so").read_bytes()
    assert v1["build"] == "zve1_202" and v1["artifact_sha256"]["libmpr.so"] == hashlib.sha256(lm).hexdigest(), "another libmpr.so"
    hits, k = [], lm.find(STOCK)
    while k >= 0:
        hits.append(k)
        k = lm.find(STOCK, k + 1)
    assert hits == [0x207D8C, 0x207DD8, LOOKALIKE] and lm[LOOKALIKE + 4:LOOKALIKE + 8] == W4096
    optional = {int(p["file_off"], 16): p for p in v1["optional_sites"]}
    assert sorted(optional) == [a for a, _, _, _ in SITES]
    patches = []
    for off, what, fourcc, a7iv in SITES:
        p = optional[off]
        assert p["binary"] == "libmpr.so" and p["code"] and bytes.fromhex(p["old"]) == STOCK and bytes.fromhex(p["new"]) == NEW
        assert lm[off:off + 4] == STOCK and lm[off + 4:off + 8] == W3840 and (lm[off - 8:off] + lm[off + 4:off + 12]).hex() == NEIGHBOURS[off]
        assert sample_entry(lm, off) == fourcc
        patches.append({"binary": "libmpr.so", "kind": "L4-mp4size", "file_off": hex(off), "va": hex(off), "old": STOCK.hex(), "new": NEW.hex(),
                        "note": "MP4 track height, %s: 2160 -> 2560 (`mov w6, #0x870` -> `mov w6, #0xa00`; A7 IV %#x)" % (what, a7iv), "code": True})
    v2 = {}
    for key, val in v1.items():
        if key == "optional_sites":
            continue
        v2[key] = val
        if key == "design":
            v2[key] = "ogfile2560_hs_s_zv_v2"
        elif key == "generated_by":
            v2[key] = "modding/zve1/build_ogfile_meta_zv.py (ogfile2560_hs_s_zv_v1 and its two optional_sites)"
        elif key == "summary":
            lms = [p for p in v1["patches"] if p["binary"] == "libmpr.so"] + patches
            v2[key] = dict(val, **{"libmpr.so": {"sites": len(lms), "bytes": sum(len(p["old"]) // 2 for p in lms), "code_sites": len(patches)}})
        elif key == "sites_by_kind":
            v2[key] = dict(val, **{"L4-mp4size": len(patches)})
        elif key == "while_applied":
            v2[key] = [x for x in val if "container" not in x] + [
                "the MP4 headers (tkhd, the stsd entry, Sony's PROF box) say 3840 by 2560 for every 3840-wide AVC or HEVC recording, whatever the "
                "frame rate; Sony's XML (the M01.XML beside the file and the one inside it) still says 3840 by 2160, 16:9",
                "the two libmpr.so instructions stay changed until a cold boot or the put back, also if the open-gate state itself is gone: "
                "a 16:9 recording then has 2560 in its headers"]
        elif key == "patches":
            v2[key] = val + patches
    v2["changes_from_v1"] = ["the two optional_sites of v1 (MP4 track height, 0x207d8c and 0x207dd8) are sites, as in the A7 IV's ogfile2560_hs_s_v2; "
                             "the 4096-wide case 0x207f3c is not touched"]
    dst = DES / "ogfile2560_hs_s_zv_v2.json"
    dst.write_text(json.dumps(v2, indent=1) + "\n", encoding="utf8", newline="\n")
    print("ogfile2560_hs_s_zv_v2: %d sites (%d code) -> %s" % (len(v2["patches"]), len(patches), dst))


if __name__ == "__main__":
    main()
