"""Build libJit_zv_burst.so and run it in Unicorn ARM64 against a simulated camera.
  zve1fw\\.venv_build\\Scripts\\python.exe -I -B build_and_test.py
"""
import hashlib, shutil, struct, subprocess, sys
from pathlib import Path
from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_INTR
from unicorn import arm64_const as A

HERE = Path(__file__).resolve().parent
CT6 = Path(__file__).resolve().parents[3] / Path(r"windows\tools\camera_tests\CT6_memory_read_check")
SEN = Path(r"zve1fw\out\firmware.tar_unpacked\0700_part_image\dev\nflasha15_unpacked\lib\libsencore.so")
IMG = Path(r"zve1fw\bins\cpapp-b.bin").read_bytes()
assert hashlib.sha256(IMG).hexdigest().startswith("8e1ee4c48ee1")
BASE = 0x108000
# pages holding the code this reading interprets: interval calculation, its debug override, the timer and the mode choice
PAGES = (0x493000, 0x46B000, 0xAEF000, 0xAF0000, 0x4F2000)
SO = HERE / "libJit_zv_burst.so"


def build():
    h = ["/* generated from cpapp-b.bin 2.02 */", "struct code_page { u32 address; u8 sha256[32]; };", "static const struct code_page code_pages[] = {"]
    for a in PAGES:
        d = hashlib.sha256(IMG[a - BASE:a - BASE + 4096]).digest()
        h.append("    { 0x%x, { %s } }," % (a, ", ".join("0x%02x" % x for x in d)))
    (HERE / "burst_pages.h").write_text("\n".join(h + ["};"]) + "\n", encoding="ascii")
    subprocess.run([sys.executable, "-m", "ziglang", "cc", "-target", "aarch64-linux-gnu", "-std=gnu11", "-O1", "-Wall", "-Wextra", "-Werror",
                    "-Wno-unused-function", "-Wno-unused-const-variable", "-Wno-unused-variable", "-fPIC", "-shared", "-nostdlib", "-ffreestanding",
                    "-fno-stack-protector", "-fno-builtin", "-fno-asynchronous-unwind-tables", "-Wl,-soname,libJit.so", "-Wl,--no-undefined",
                    "-Wl,-z,now", "-g0", "-s", "-Wl,-z,max-page-size=4096", "-DDUMP=0", "-I", str(HERE), "-I", str(CT6 / "helper_zv"),
                    str(HERE / "burstread.c"), str(SEN), "-o", str(SO)], check=True, cwd=HERE)


def run(ram):
    elf = SO.read_bytes()
    off, es, num = struct.unpack_from("<Q", elf, 0x20)[0], *struct.unpack_from("<HH", elf, 0x36)
    ph = [struct.unpack_from("<IIQQQQQQ", elf, off + k * es) for k in range(num)]
    SOB, STUB, BUF, PHYS, STACK, STOP = 0x10000000, 0x20000000, 0x30000000, 0x410000000, 0x40000000, 0x50000000
    mu = Uc(UC_ARCH_ARM64, UC_MODE_ARM)
    mu.reg_write(A.UC_ARM64_REG_CPACR_EL1, mu.reg_read(A.UC_ARM64_REG_CPACR_EL1) | (3 << 20))
    for base, size in ((SOB, 0x100000), (STUB, 0x1000), (BUF, 0x2000), (STACK, 0x100000), (STOP, 0x1000)):
        mu.mem_map(base, size)
    for p in ph:
        if p[0] == 1:
            mu.mem_write(SOB + p[3], elf[p[2]:p[2] + p[5]])
    va2off = lambda va: next(p[2] + va - p[3] for p in ph if p[0] == 1 and p[3] <= va < p[3] + p[5])
    dyn = next(p for p in ph if p[0] == 2)
    tags, needed = {}, []
    for o in range(dyn[2], dyn[2] + dyn[5], 16):
        t, v = struct.unpack_from("<qQ", elf, o)
        if t == 0:
            break
        needed.append(v) if t == 1 else tags.__setitem__(t, v)
    cstr = lambda o: elf[o:elf.index(b"\0", o)].decode()
    assert [cstr(va2off(tags[5]) + n) for n in needed] == ["libsencore.so"]
    name = lambda i: cstr(va2off(tags[5]) + struct.unpack_from("<I", elf, va2off(tags[6]) + 24 * i)[0])
    stubs = {"_Z9dmm_allocjPj": STUB, "_Z8dmm_freej": STUB + 16, "sen_dma_transfer": STUB + 32}
    for a in stubs.values():
        mu.mem_write(a, struct.pack("<I", 0xD65F03C0))
    for t, s in ((7, 8), (23, 2)):
        for o in range(va2off(tags[t]), va2off(tags[t]) + tags[s], 24) if t in tags else ():
            where, info, add = struct.unpack_from("<QQq", elf, o)
            val = SOB + add if info & 0xFFFFFFFF == 1027 else stubs[name(info >> 32)]
            mu.mem_write(SOB + where, struct.pack("<Q", val))
    st = {"out": bytearray(), "dma": [], "opens": [], "alloc": 0}
    X = lambda n: getattr(A, "UC_ARM64_REG_X%d" % n)

    def ret(v):
        mu.reg_write(X(0), v & 0xFFFFFFFFFFFFFFFF)
        mu.reg_write(A.UC_ARM64_REG_PC, mu.reg_read(A.UC_ARM64_REG_LR))

    def alloc(*_):
        mu.mem_write(mu.reg_read(X(1)), struct.pack("<I", 1)); st["alloc"] += 1; ret(PHYS)

    def free(*_):
        st["alloc"] -= 1; ret(0)

    def dma(*_):
        d, src, dst, n = (mu.reg_read(X(i)) for i in range(4))
        assert d == 0 and dst == PHYS and n == 4096 and src % 4096 == 0, "only coprocessor -> buffer page reads are allowed"
        st["dma"].append(src); mu.mem_write(BUF, bytes(ram[src:src + n])); ret(0)

    for fn, a in ((alloc, STUB), (free, STUB + 16), (dma, STUB + 32)):
        mu.hook_add(UC_HOOK_CODE, fn, begin=a, end=a + 3)

    def svc(*_):
        nr, a = mu.reg_read(X(8)), [mu.reg_read(X(i)) for i in range(6)]
        r = 0
        if nr == 56:
            p = bytearray()
            while (c := mu.mem_read(a[1] + len(p), 1)[0]):
                p.append(c)
            p = p.decode(); st["opens"].append((p, a[2]))
            if p.endswith("readcheck_result.txt"):
                r = 10
            else:
                assert p == "/dev/mem" and a[2] & 3 == 0, ("unexpected or writable open", p, a[2])
                r = 11
        elif nr == 64:
            assert a[0] == 10, "write to something that is not the result file"
            st["out"] += mu.mem_read(a[1], a[2]); r = a[2]
        elif nr == 222:
            assert a[4] == 11 and a[2] == 1, "mapping must be of /dev/mem and read-only"
            r = BUF
        elif nr not in (57, 215):
            raise AssertionError("unexpected syscall %d" % nr)
        mu.reg_write(X(0), r)

    mu.hook_add(UC_HOOK_INTR, svc)
    mu.reg_write(A.UC_ARM64_REG_SP, STACK + 0xF0000)
    mu.reg_write(A.UC_ARM64_REG_LR, STOP)
    ctor = struct.unpack("<Q", mu.mem_read(SOB + tags[25], 8))[0]
    assert tags[27] == 8, "exactly one constructor"
    mu.emu_start(ctor, STOP, count=50_000_000)
    assert st["alloc"] == 0, "buffer leaked"
    return st["out"].decode(), st


def main():
    build()
    so = SO.read_bytes()
    ram = bytearray(0x2700000)
    ram[BASE:BASE + len(IMG)] = IMG
    ram[0x19967A7] = 0x00
    ram[0x1A08998:0x1A089D0] = bytes(range(56))
    ram[0x197DEFC:0x197DF00] = struct.pack("<I", 100)
    before = bytes(ram)
    out, st = run(ram)
    assert out.startswith("zvburst 1") and "VERDICT READ OK" in out and out.rstrip().endswith("== done"), out
    got = {l.split()[1]: (int(l.split()[2], 16), bytes.fromhex(l.split()[3])) for l in out.splitlines() if l.startswith("data ")}
    assert len(got) == 4 and all(ram[a:a + len(b)] == b for a, b in got.values()), "bytes reported differ from memory"
    assert bytes(ram) == before
    print("PASS read: 4 ranges match memory; %d DMA transfers, all coprocessor -> buffer; /dev/mem read-only" % len(st["dma"]))
    bad = bytearray(ram)
    bad[0x493D90] ^= 1
    out2, st2 = run(bad)
    assert "no data was read" in out2 and not any(l.startswith("data ") for l in out2.splitlines()) and "VERDICT" not in out2
    assert all(a in PAGES for a in st2["dma"])
    print("PASS refusal: one changed code byte -> no data address is read")
    shutil.copy2(SO, CT6 / "helper_zv_custom" / SO.name)
    print(hashlib.sha256(so).hexdigest(), len(so), SO.name)
    (HERE / "sample_result.txt").write_text(out, encoding="utf8")


if __name__ == "__main__":
    main()
