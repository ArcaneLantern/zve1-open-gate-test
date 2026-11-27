"""H19/H20: XAVC S 4K 25p 100M 4:2:0 8-bit -> HEVC 4:2:0 10-bit, RAM only (libmpr.so, ZV-E1 2.02).

Writes expected_mp_hevc25_zv_v1.h and hevc25_zv_v1.json, then compiles readcheck.c levels 19/20 (unmodified).
  zve1fw\\.venv_build\\Scripts\\python.exe -I -B build_h19.py
"""
import hashlib
import json
import shutil
import struct
import subprocess
import sys
from pathlib import Path

import capstone

HERE = Path(__file__).resolve().parent
REPO = Path(__file__).resolve().parents[3]
CT6 = REPO / "windows/tools/camera_tests/CT6_memory_read_check"
NAME = "hevc25_zv_v1"

LM = Path(r"zve1fw\bins\libmpr.so").read_bytes()
AV = Path(r"zve1fw\bins\av-cam.bin").read_bytes()
assert hashlib.sha256(LM).hexdigest() == "e45dde41291cf45dd80897e0d9fa03818c1cdc14ae4d466c64f3d48af419e7cd"
assert hashlib.sha256(AV).hexdigest() == "36b49addab28db7010966b2ac2b89b75a0c99e8a8fa0e33c331f2733d15eb455"

CAVE, CAVE_END = 0x67000, 0x67100          # inside .rela.dyn (ends at 0x678f8 = .rela.plt): relocations applied once at load
MEMCPY_PLT, NORM_FPS = 0x735a0, 0xf15f4
HOOK_PARAM, HOOK_RATE, HOOK_HVCC = 0xe1bc0, 0xf18bc, 0x207aa4

NOP = 0xD503201F
# Each stub: assembly lines; "@bl X" / "@b X" become a branch to address X (encoded here, not by the assembler).
STUBS = {
    "param": [  # replaces `bl memcpy`: copy, then VPC 0 (AVC 420 8) -> 5 (HEVC 420 10) when quality 12 (100M) and frame rate 2 (25p)
        "stp x29, x30, [sp, #-16]!", "mov x29, sp", ("bl", MEMCPY_PLT),
        "ldr w9, [x23, #0x178]", "cbnz w9, 1f",
        "ldr w9, [x23, #0x17c]", "cmp w9, #12", "b.ne 1f",
        "ldr w9, [x23, #0x180]", "cmp w9, #2", "b.ne 1f",
        "mov w9, #5", "str w9, [x23, #0x178]",
        "1: ldp x29, x30, [sp], #16", "ret"],
    "rate": [   # replaces `bl norm_fps` in the HEVC Long 4K rate check: class 2 (no table row) -> 3
        "stp x29, x30, [sp, #-16]!", "mov x29, sp", ("bl", NORM_FPS),
        "cmp w0, #2", "b.ne 1f", "mov w0, #3",
        "1: ldp x29, x30, [sp], #16", "ret"],
    "hvcc": [   # replaces `cmp w0, #0x870`: flags are "equal" for height 2160 or 2560
        "cmp w0, #0x870", "b.eq 1f", "cmp w0, #0xa00", ("1: b", HOOK_HVCC + 4)],
}


def branch(op, src, dst):
    d = dst - src
    assert d % 4 == 0 and -(1 << 27) <= d < (1 << 27)
    return struct.pack("<I", (0x94000000 if op == "bl" else 0x14000000) | ((d >> 2) & 0x3FFFFFF))


def zig(*args):
    subprocess.run([sys.executable, "-m", "ziglang", *args], check=True, cwd=HERE)


def text_of(obj):
    b = obj.read_bytes()
    shoff = struct.unpack_from("<Q", b, 0x28)[0]
    es, n, sx = struct.unpack_from("<HHH", b, 0x3a)
    sh = [struct.unpack_from("<IIQQQQ", b, shoff + i * es) for i in range(n)]
    names = sh[sx][4]
    for s in sh:
        if b[names + s[0]:].split(b"\0", 1)[0] == b".text":
            return b[s[4]:s[4] + s[5]]
    raise RuntimeError("no .text")


def assemble():
    code, entry = bytearray(), {}
    for name, lines in STUBS.items():
        entry[name] = CAVE + len(code)
        src, fix = [], []
        for k, ln in enumerate(lines):
            if isinstance(ln, tuple):
                op = ln[0].split()[-1]
                src.append(("1: " if ln[0].startswith("1:") else "") + "nop")
                fix.append((k, op, ln[1]))
            else:
                src.append(ln)
        s = HERE / f"stub_{name}.s"
        s.write_text(".text\n" + "\n".join(src) + "\n", encoding="ascii")
        o = HERE / f"stub_{name}.o"
        zig("cc", "-target", "aarch64-linux-gnu", "-c", s.name, "-o", o.name)
        t = bytearray(text_of(o)[:4 * len(lines)])
        for k, op, dst in fix:
            assert struct.unpack_from("<I", t, 4 * k)[0] == NOP
            t[4 * k:4 * k + 4] = branch(op, entry[name] + 4 * k, dst)
        md = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)
        ins = list(md.disasm(bytes(t), entry[name]))
        assert len(ins) == len(lines)
        print(f"-- {name} @ {entry[name]:#x}")
        for i in ins:
            print(f"   {i.address:#x}  {i.mnemonic} {i.op_str}")
        code += t
    assert len(code) <= CAVE_END - CAVE, len(code)
    return bytes(code), entry


def main():
    code, entry = assemble()
    sites = []   # apply order: the whole cave first, then the hooks (MP_LM_ORDERED reverses it for the put back)
    for k in range(0, len(code), 16):
        new = code[k:k + 16]
        sites.append(("cave", CAVE + k, LM[CAVE + k:CAVE + k + len(new)], new))
    for off, op, name, stock in ((HOOK_PARAM, "bl", "param", ("bl", MEMCPY_PLT)), (HOOK_RATE, "bl", "rate", ("bl", NORM_FPS)),
                                 (HOOK_HVCC, "b", "hvcc", None)):
        old = LM[off:off + 4]
        assert old == (branch(stock[0], off, stock[1]) if stock else bytes.fromhex("1fc02171")), hex(off)
        sites.append(("hook", off, old, branch(op, off, entry[name])))
    assert all(o != n for _, _, o, n in sites)

    # guards: file header, 8 bytes before the cave, 16 bytes on each side of every hook, the two functions the cave calls
    guards = [(0, LM[:16]), (CAVE - 8, LM[CAVE - 8:CAVE])]
    for off in (HOOK_PARAM, HOOK_RATE, HOOK_HVCC):
        guards += [(off - 16, LM[off - 16:off]), (off + 4, LM[off + 4:off + 20])]
    guards += [(MEMCPY_PLT, LM[MEMCPY_PLT:MEMCPY_PLT + 16]), (NORM_FPS, LM[NORM_FPS:NORM_FPS + 16])]

    # must not touch what M19 (ogfile2560_hs_s_zv_v2) changes, so H19 works with or without it
    m19 = json.loads((REPO / "windows/tools/modding/designs/ogfile2560_hs_s_zv_v2.json").read_text(encoding="utf8"))
    spans = [(a, len(o)) for _, a, o, _ in sites] + [(a, len(b)) for a, b in guards]
    for p in m19["patches"]:
        if p["binary"] == "libmpr.so":
            a, n = int(p["file_off"], 16), len(p["old"]) // 2
            assert not any(a < s + m and s < a + n for s, m in spans), f"overlaps M19 at {a:#x}"

    # av-cam.bin: the two read-only guards every level 19 design carries (unit-type row, clip row)
    avg = [(0x38F848 + 0x20, AV[0x38F848 + 0x20:0x38F848 + 0x30]), (0x38D7EC + 0x50, AV[0x38D7EC + 0x50:0x38D7EC + 0x60])]
    assert struct.unpack("<4I", avg[0][1]) == (0x486, 0x474, 0x477, 0x47A)
    first = avg[1][0] & ~0xFFF if avg[1][0] < avg[0][0] else avg[0][0] & ~0xFFF
    span = ((max(a + len(b) for a, b in avg) - first) + 0xFFF) & ~0xFFF

    hx = lambda b: ", ".join("0x%02x" % x for x in b.ljust(16, b"\0"))
    row = lambda a, kind, old, new: "    { 0x%x, %d, %d, { %s }, { %s } }," % (a, len(old), kind, hx(old), hx(new))
    table = [(a, 0, b, b"") for a, b in guards] + [(a, 1, o, n) for _, a, o, n in sites]
    ordered = sorted(table)
    assert all(ordered[k][0] + len(ordered[k][2]) <= ordered[k + 1][0] for k in range(len(ordered) - 1)), "entries overlap"
    out = ["/* Generated by build_h19.py. Do not edit. kind 1: a site; kind 0: a guard (must be as in the file). */",
           '#define MP_DESIGN "%s"' % NAME, "#define MP_LM_ORDERED 1",
           "#define MP_AV_FIRST 0x%xUL" % first, "#define MP_AV_BYTES 0x%xUL" % span,
           "struct mp_site { u32 off; u8 len; u8 kind; u8 stock[16]; u8 changed[16]; };",
           "static const struct mp_site mp_av[] = {"] + [row(a, 0, b, b"") for a, b in sorted(avg)] + \
          ["};", "static const struct mp_site mp_lm[] = {"] + [row(*t) for t in table] + ["};"]
    (HERE / f"expected_mp_{NAME}.h").write_text("\n".join(out) + "\n", encoding="utf8", newline="\n")
    (HERE / f"{NAME}.json").write_text(json.dumps({
        "design": NAME, "build": "zve1_202", "artifact_sha256": {"libmpr.so": hashlib.sha256(LM).hexdigest()},
        "entry": entry, "sites": [{"kind": k, "off": hex(a), "old": o.hex(), "new": n.hex()} for k, a, o, n in sites],
        "guards": [{"off": hex(a), "bytes": b.hex()} for a, b in guards]}, indent=1), encoding="utf8")

    shas = {}
    for lvl in (19, 20):
        so = HERE / f"libJit_zv_H{lvl}.so"
        zig("cc", "-target", "aarch64-linux-gnu", "-std=gnu11", "-O1", "-Wall", "-Wextra", "-Werror", "-fPIC", "-shared", "-nostdlib",
            "-ffreestanding", "-fno-stack-protector", "-fno-builtin", "-fno-asynchronous-unwind-tables", "-Wl,-soname,libJit.so",
            "-Wl,--no-undefined", "-Wl,-z,now", "-g0", "-s", "-Wl,-z,max-page-size=4096", f"-DLEVEL={lvl}",
            f'-DMP_H="expected_mp_{NAME}.h"', "-DAVCAM_PHYS=0x401000000UL", "-I", str(HERE), str(CT6 / "helper/readcheck.c"), "-o", so.name)
        shas[so.name] = (hashlib.sha256(so.read_bytes()).hexdigest(), so.stat().st_size)
        shutil.copy2(so, CT6 / "helper_zv_custom" / so.name)
    for n, (h, size) in shas.items():
        print(h, size, n)
    print(len(sites), "sites,", len(guards), "guards")


if __name__ == "__main__":
    main()
