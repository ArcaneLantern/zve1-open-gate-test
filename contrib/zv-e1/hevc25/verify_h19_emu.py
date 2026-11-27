"""Unicorn ARM64 checks for H19/H20.  A: the patched libmpr.so code itself.  B: the compiled .so files against a simulated camera.
  zve1fw\\.venv_build\\Scripts\\python.exe -I -B verify_h19_emu.py
"""
import json
import struct
from pathlib import Path

from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_INTR
from unicorn import arm64_const as A

HERE = Path(__file__).resolve().parent
LM = Path(r"zve1fw\bins\libmpr.so").read_bytes()
AV = Path(r"zve1fw\bins\av-cam.bin").read_bytes()
D = json.loads((HERE / "hevc25_zv_v1.json").read_text(encoding="utf8"))
M19 = json.loads((Path(__file__).resolve().parents[3] / Path(r"windows\tools\modding\designs\ogfile2560_hs_s_zv_v2.json"))
                 .read_text(encoding="utf8"))
SITES = [(int(s["off"], 16), bytes.fromhex(s["old"]), bytes.fromhex(s["new"]), s["kind"]) for s in D["sites"]]
LOAD0 = 0x2C7EE4
X = lambda n: getattr(A, "UC_ARM64_REG_X%d" % n)


def patched(img, back=False):
    b = bytearray(img)
    for a, old, new, _ in SITES:
        b[a:a + len(old)] = old if back else new
    return bytes(b)


# ---------------------------------------------------------------- A: the patched code
def machine(img):
    mu = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    mu.mem_map(0, 0x2C8000)
    mu.mem_write(0, img[:LOAD0])
    mu.mem_map(0x300000, 0x100000)          # bss: g_movieRecParam 0x370c50
    mu.mem_map(0x500000, 0x20000)           # source struct and stack
    mu.reg_write(A.UC_ARM64_REG_SP, 0x51F000)

    def memcpy(uc, *_):
        d, s, n = (uc.reg_read(X(i)) for i in range(3))
        uc.mem_write(d, bytes(uc.mem_read(s, n)))
        uc.reg_write(A.UC_ARM64_REG_PC, uc.reg_read(A.UC_ARM64_REG_LR))
    mu.hook_add(UC_HOOK_CODE, memcpy, begin=0x735A0, end=0x735A3)
    return mu


def check_param(img):
    mu, dst, src, n = machine(img), 0x370C50, 0x500000, 0
    for vpc in (0, 1, 2, 5, 7, 13):
        for q in (0, 11, 12, 13, 26, 49):
            for fps in (0, 1, 2, 3, 4, 5, 8):
                p = bytearray((i * 7) & 0xFF for i in range(0x1D5))
                struct.pack_into("<3I", p, 0x178, vpc, q, fps)
                mu.mem_write(src, bytes(p))
                mu.mem_write(dst, bytes(0x200))
                for r, v in ((0, dst), (1, src), (2, 0x1D5), (23, dst)):
                    mu.reg_write(X(r), v)
                sp = mu.reg_read(A.UC_ARM64_REG_SP)
                mu.emu_start(0xE1BC0, 0xE1BC4, count=100)
                assert mu.reg_read(A.UC_ARM64_REG_PC) == 0xE1BC4 and mu.reg_read(A.UC_ARM64_REG_SP) == sp and mu.reg_read(X(23)) == dst
                if (vpc, q, fps) == (0, 12, 2):
                    struct.pack_into("<I", p, 0x178, 5)
                assert bytes(mu.mem_read(dst, 0x1D5)) == bytes(p), (vpc, q, fps)
                assert bytes(mu.mem_read(dst + 0x1D5, 0x200 - 0x1D5)) == bytes(0x200 - 0x1D5)
                n += 1
    print(f"PASS A1 SetMovieRecParam: {n} combinations, only (VPC 0, quality 12, fps 2) becomes VPC 5")


def check_rate(stock, img):
    for fps in range(0, 24):
        out = []
        for code, begin in ((stock, 0xF18BC), (img, 0xF18BC)):
            mu = machine(code)
            mu.reg_write(X(0), fps)
            mu.reg_write(X(20), 0x1234)
            mu.emu_start(begin, 0xF18C0, count=100)
            assert mu.reg_read(A.UC_ARM64_REG_PC) == 0xF18C0 and mu.reg_read(X(20)) == 0x1234
            out.append(mu.reg_read(X(0)) & 0xFFFFFFFF)
        assert out[1] == (3 if out[0] == 2 else out[0]), (fps, out)
    print("PASS A2 HEVC rate check: class 2 -> 3, every other class unchanged (fps 0..23)")


def level(img, height, rate, four_k=True):
    """4K path: run to the function's return and give (0x207b20, level). Else stop just after falling through the compare."""
    mu = machine(img)
    mu.reg_write(A.UC_ARM64_REG_LR, 0x500800)
    mu.mem_write(0x500000, bytes(0x100))
    mu.mem_write(0x500020, struct.pack("<I", rate))
    mu.mem_write(0x500028, struct.pack("<H", height))
    mu.reg_write(X(1), 0x500000)
    mu.reg_write(X(0), height)
    first = []
    mu.hook_add(UC_HOOK_CODE, lambda uc, a, *_: first.append(a) if a in (0x207B20, 0x207AAC) and not first else None)
    mu.emu_start(0x207AA4, 0x500800 if four_k else 0x207AB0, count=40)
    return first[0], mu.reg_read(X(0)) & 0xFFFF


def check_hvcc(stock, img):
    rates = (25000, 50000, 97000, 100000, 140000, 200000)
    for r in rates:
        assert level(img, 2160, r) == level(stock, 2160, r)
        assert level(img, 2560, r) == level(stock, 2160, r)
    for h in (720, 1080, 2161, 2559, 4320):
        assert level(img, h, 100000, False)[0] == level(stock, h, 100000, False)[0] == 0x207AAC
    assert level(stock, 2560, 100000, False)[0] == 0x207AAC
    print("PASS A3 hvcC level: 2560 takes the 2160 path; other heights unchanged;", {r: hex(level(img, 2560, r)[1]) for r in rates})


# ---------------------------------------------------------------- B: the .so files
def run_so(path, lm_mem, av_mem, fail_on_write=None):
    elf = path.read_bytes()
    assert elf[:4] == b"\x7fELF" and struct.unpack_from("<H", elf, 0x12)[0] == 183 and len(elf) <= 65520
    off, es, num = struct.unpack_from("<Q", elf, 0x20)[0], *struct.unpack_from("<HH", elf, 0x36)
    ph = [struct.unpack_from("<IIQQQQQQ", elf, off + k * es) for k in range(num)]
    SO, LIB, AVVA, STACK, STOP = 0x10000000, 0x7F00000000, 0x60000000, 0x40000000, 0x50000000
    mu = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    mu.reg_write(A.UC_ARM64_REG_CPACR_EL1, mu.reg_read(A.UC_ARM64_REG_CPACR_EL1) | (3 << 20))
    for base, size in ((SO, 0x100000), (LIB, 0x2C8000), (AVVA, 0x100000), (STACK, 0x100000), (STOP, 0x1000)):
        mu.mem_map(base, size)
    for p in ph:
        if p[0] == 1:
            mu.mem_write(SO + p[3], elf[p[2]:p[2] + p[5]])
    mu.mem_write(LIB, bytes(lm_mem))
    dyn = next(p for p in ph if p[0] == 2)
    tags = {}
    for o in range(dyn[2], dyn[2] + dyn[5], 16):
        t, v = struct.unpack_from("<qQ", elf, o)
        if t == 0:
            break
        assert t != 1, "unexpected DT_NEEDED"
        tags[t] = v
    va2off = lambda va: next(p[2] + va - p[3] for p in ph if p[0] == 1 and p[3] <= va < p[3] + p[5])
    for t, s in ((7, 8), (23, 2)):
        for o in range(va2off(tags[t]), va2off(tags[t]) + tags[s], 24) if t in tags else ():
            where, info, add = struct.unpack_from("<QQq", elf, o)
            assert info & 0xFFFFFFFF == 1027, "only RELATIVE relocations expected"
            mu.mem_write(SO + where, struct.pack("<Q", SO + add))
    ctor = struct.unpack("<Q", mu.mem_read(SO + tags[25], 8))[0]
    st = {"out": bytearray(), "writes": [], "files": {}, "next": 10, "av": None}
    maps = ("7f00000000-7f002c8000 r-xp 00000000 fd:00 42 /usr/lib/libmpr.so\n").encode()

    def cstr(va):
        out = bytearray()
        while (c := mu.mem_read(va + len(out), 1)[0]):
            out.append(c)
        return out.decode()

    def svc(uc, *_):
        nr, a = uc.reg_read(X(8)), [uc.reg_read(X(i)) for i in range(6)]
        ret = 0
        if nr == 56:
            ret = st["next"]
            st["next"] += 1
            st["files"][ret] = [cstr(a[1]), 0]
        elif nr == 57:
            st["files"].pop(a[0])
        elif nr == 63:
            name, pos = st["files"][a[0]]
            chunk = maps[pos:pos + a[2]] if name == "/proc/self/maps" else b""
            uc.mem_write(a[1], chunk) if chunk else None
            st["files"][a[0]][1] += len(chunk)
            ret = len(chunk)
        elif nr == 64:
            assert st["files"][a[0]][0].endswith("readcheck_result.txt")
            st["out"] += uc.mem_read(a[1], a[2])
            ret = a[2]
        elif nr == 67:                                      # pread64: the kernel's view of av-cam.bin
            assert st["files"][a[0]][0] == "/dev/mem"
            o = a[3] - 0x401000000
            uc.mem_write(a[1], bytes(av_mem[o:o + a[2]]))
            ret = a[2]
        elif nr == 68:                                      # pwrite64: /proc/self/mem only
            assert st["files"][a[0]][0] == "/proc/self/mem" and LIB <= a[3] and a[3] + a[2] <= LIB + LOAD0
            st["writes"].append(a[3] - LIB)
            if len(st["writes"]) == fail_on_write:
                ret = -5
            else:
                uc.mem_write(a[3], bytes(uc.mem_read(a[1], a[2])))
                ret = a[2]
        elif nr == 222:                                     # mmap of the av-cam.bin pages
            assert st["files"][a[4]][0] == "/dev/mem"
            st["av"] = (a[5] - 0x401000000, a[1])
            uc.mem_write(AVVA, bytes(av_mem[st["av"][0]:st["av"][0] + a[1]]))
            ret = AVVA
        elif nr == 215:
            o, n = st["av"]
            assert bytes(uc.mem_read(AVVA, n)) == bytes(av_mem[o:o + n]), "av-cam.bin was written"
            st["av"] = None
        elif nr == 61:                                      # getdents64: nothing to list
            ret = 0
        elif nr == 175:
            ret = 0
        else:
            raise AssertionError(f"unhandled syscall {nr}")
        uc.reg_write(X(0), ret & 0xFFFFFFFFFFFFFFFF)

    mu.hook_add(UC_HOOK_INTR, svc)
    mu.reg_write(A.UC_ARM64_REG_SP, STACK + 0xF0000)
    mu.reg_write(A.UC_ARM64_REG_LR, STOP)
    mu.emu_start(ctor, STOP, count=100_000_000)
    assert mu.reg_read(A.UC_ARM64_REG_PC) == STOP and not st["files"] and st["av"] is None, "did not finish cleanly"
    return st["out"].decode(), bytes(mu.mem_read(LIB, 0x2C8000)), st["writes"]


def check_so():
    h19, h20 = HERE / "libJit_zv_H19.so", HERE / "libJit_zv_H20.so"
    stock = LM[:LOAD0].ljust(0x2C8000, b"\0")
    m19 = bytearray(stock)
    for p in M19["patches"]:
        if p["binary"] == "libmpr.so":
            o, new = int(p["file_off"], 16), bytes.fromhex(p["new"])
            m19[o:o + len(new)] = new
    order = [a for a, *_ in SITES]
    for label, base in (("stock", stock), ("with M19 applied", bytes(m19))):
        rep, applied, w = run_so(h19, base, AV)
        assert rep.startswith("readcheck 1 level 19\n") and "DONE: every site holds the target bytes (apply)" in rep, rep
        assert applied == patched(base) and w == order, "wrong bytes or order"
        rep, again, w = run_so(h19, applied, AV)
        assert "NOTHING TO DO" in rep and again == applied and not w, rep
        rep, back, w = run_so(h20, applied, AV)
        assert "DONE: every site holds the target bytes (put back)" in rep and back == base and w == order[::-1], rep
        print(f"PASS B1 {label}: apply (cave first, hooks last), re-apply no-op, put back bit-exact (hooks first)")
    for what, at in (("hook byte", 0xE1BC0), ("cave byte", 0x67011), ("guard byte", 0xF15F4)):
        bad = bytearray(stock)
        bad[at] ^= 1
        rep, after, w = run_so(h19, bytes(bad), AV)
        assert "nothing is written" in rep and after == bytes(bad) and not w, rep
        print(f"PASS B2 refuses a changed {what}, 0 writes")
    av_bad = bytearray(AV)
    av_bad[0x38F868] ^= 1
    rep, after, w = run_so(h19, stock, bytes(av_bad))
    assert "nothing is written" in rep and after == stock and not w, rep
    print("PASS B3 refuses another av-cam.bin, 0 writes")
    for src, so, base in (("apply", h19, stock), ("put back", h20, patched(stock))):
        for n in range(1, len(SITES) + 1):
            rep, after, _ = run_so(so, base, AV, fail_on_write=n)
            assert "NOT DONE: a step failed" in rep and after == base, (src, n, rep)
        print(f"PASS B4 {src}: a failure at each of the {len(SITES)} writes is rolled back bit-exact")


if __name__ == "__main__":
    after = patched(LM)
    check_param(after)
    check_rate(LM, after)
    check_hvcc(LM, after)
    check_so()
    print("ALL PASS")
