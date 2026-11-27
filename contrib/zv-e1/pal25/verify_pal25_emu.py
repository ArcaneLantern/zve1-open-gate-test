"""AArch64 ELF structural audit + full Unicorn execution verification
of compiled libJit_zv_L5_pal25.so and libJit_zv_L6_pal25.so.

Runs 6 test scenarios against simulated ZV-E1 coprocessor RAM loaded with
real cpapp-b.bin + real PAL (hz=1) emulated stored_records:
  1. Fresh apply (L5_pal25) on PAL stock (with 0xAA poison in uninit padding)
  2. Idempotent re-apply (L5_pal25)
  3. Full putback (L6_pal25) -> bit-for-bit identical to stock PAL RAM
  4. Safety refusal on NTSC (hz=0) stored record
  5. Safety refusal on 1-byte mismatch at 0xdcdd50
  6. Mid-apply rollback/undo on 10th write failure -> bit-for-bit stock PAL RAM
"""
import json
import struct
import sys
from pathlib import Path

from unicorn import Uc, UC_ARCH_ARM64, UC_MODE_ARM, UC_HOOK_CODE, UC_HOOK_INTR
from unicorn.arm64_const import (
    UC_ARM64_REG_CPACR_EL1,
    UC_ARM64_REG_LR,
    UC_ARM64_REG_PC,
    UC_ARM64_REG_SP,
    UC_ARM64_REG_X0,
    UC_ARM64_REG_X1,
    UC_ARM64_REG_X2,
    UC_ARM64_REG_X3,
    UC_ARM64_REG_X4,
    UC_ARM64_REG_X5,
    UC_ARM64_REG_X8,
)

PAL25_DIR = Path(r"zve1fw\pal25")
sys.path.insert(0, str(PAL25_DIR))
import build_og_pal25_zv as B  # noqa: E402

L5_SO = PAL25_DIR / "libJit_zv_L5_pal25.so"
L6_SO = PAL25_DIR / "libJit_zv_L6_pal25.so"
DESIGN_JSON = PAL25_DIR / "ogsq_zv_pal25_v1.json"

BASE = B.BASE
REC_BASE = B.REC_BASE
REC_SIZE = B.REC_SIZE
MODE = B.MODE
INDEX = B.INDEX
IMAGER_ADDR = 0x17F1F64
CTRL_PTR = 0x02000000
CTRL_DRVPARAM = 0x684
OBJ_PTR = 0x02001000
CP_RAM_BASE = 0x00100000
CP_RAM_SIZE = 0x02700000  # 0x00100000 .. 0x02800000


def parse_and_audit_elf(path: Path):
    elf = path.read_bytes()
    assert len(elf) <= 65520, f"{path.name}: size {len(elf)} > 65520"
    assert elf[:4] == b"\x7fELF", f"{path.name}: not ELF"
    assert elf[4] == 2 and elf[5] == 1, f"{path.name}: not ELF64 LE"
    e_type, e_machine = struct.unpack_from("<HH", elf, 0x10)
    assert e_type == 3 and e_machine == 183, f"{path.name}: type={e_type} machine={e_machine}"

    e_phoff, = struct.unpack_from("<Q", elf, 0x20)
    e_phentsize, e_phnum = struct.unpack_from("<HH", elf, 0x36)

    loads = []
    dyn_ph = None
    for k in range(e_phnum):
        pt, pf, poff, pva, _, pfsz, pmsz, _ = struct.unpack_from("<IIQQQQQQ", elf, e_phoff + k * e_phentsize)
        if pt == 1:
            loads.append((pva, pfsz, pmsz, poff, pf))
        elif pt == 2:
            dyn_ph = (pva, pfsz, poff)
    assert dyn_ph is not None, f"{path.name}: no PT_DYNAMIC"

    def va_to_off(va: int) -> int:
        for pva, pfsz, _, poff, _ in loads:
            if pva <= va < pva + pfsz:
                return poff + (va - pva)
        raise KeyError(f"VA {hex(va)} not in file-backed PT_LOAD")

    def read_cstr(off: int) -> str:
        end = elf.find(b"\x00", off)
        return elf[off:end].decode("ascii")

    dyns = []
    off = dyn_ph[2]
    while off < dyn_ph[2] + dyn_ph[1]:
        tag, val = struct.unpack_from("<qQ", elf, off)
        off += 16
        if tag == 0:
            break
        dyns.append((tag, val))
    dmap = {t: v for t, v in dyns}

    strtab_off = va_to_off(dmap[5])  # DT_STRTAB
    symtab_off = va_to_off(dmap[6])  # DT_SYMTAB
    needed = [read_cstr(strtab_off + v) for t, v in dyns if t == 1]
    soname = read_cstr(strtab_off + dmap[14])

    assert needed == ["libsencore.so"], f"{path.name}: unexpected DT_NEEDED={needed}"
    assert soname == "libJit.so", f"{path.name}: unexpected DT_SONAME={soname}"
    assert dmap.get(27, 0) == 8, f"{path.name}: DT_INIT_ARRAYSZ={dmap.get(27)}"

    nbucket, nchain = struct.unpack_from("<II", elf, va_to_off(dmap[4]))  # DT_HASH
    undef_syms = set()
    all_syms = {}
    for si in range(nchain):
        st_name, st_info, st_other, st_shndx, st_val, st_sz = struct.unpack_from("<IBBHQQ", elf, symtab_off + si * 24)
        nm = read_cstr(strtab_off + st_name) if st_name else ""
        all_syms[si] = nm
        if si > 0 and st_shndx == 0:
            undef_syms.add(nm)

    expected_imports = {"_Z9dmm_allocjPj", "_Z8dmm_freej", "sen_dma_transfer"}
    assert undef_syms == expected_imports, f"{path.name}: undef syms {undef_syms} != {expected_imports}"

    relas = []
    for base_tag, sz_tag in ((7, 8), (23, 2)):  # DT_RELA, DT_JMPREL
        if base_tag in dmap:
            roff = va_to_off(dmap[base_tag])
            rsz = dmap[sz_tag]
            for j in range(0, rsz, 24):
                r_off, r_info, r_add = struct.unpack_from("<QQq", elf, roff + j)
                relas.append((r_off, r_info & 0xFFFFFFFF, r_info >> 32, r_add))

    return {
        "bytes": elf,
        "loads": loads,
        "init_array_va": dmap[25],
        "syms": all_syms,
        "relas": relas,
    }


def make_pal_stock_ram(img: bytes, pal_recs: dict, uninit_mode_820: set, ntsc_mode_820: bytes = None) -> bytearray:
    ram = bytearray(CP_RAM_SIZE)
    ram[BASE - CP_RAM_BASE : BASE - CP_RAM_BASE + len(img)] = img

    for mid, (idx, rec_bytes) in pal_recs.items():
        addr = REC_BASE + idx * REC_SIZE
        r = bytearray(rec_bytes)
        if mid == MODE:
            if ntsc_mode_820 is not None:
                r = bytearray(ntsc_mode_820)
            for o in uninit_mode_820:
                r[o] = 0xAA
        elif mid == 0x8C0:
            for o in uninit_mode_820:
                r[o] = 0x55
        ram[addr - CP_RAM_BASE : addr - CP_RAM_BASE + REC_SIZE] = r

    # Pointer chain: IMAGER -> CTRL -> OBJ -> {count=39, ids=0xDCC524, base=REC_BASE}
    struct.pack_into("<I", ram, IMAGER_ADDR - CP_RAM_BASE, CTRL_PTR)
    struct.pack_into("<I", ram, CTRL_PTR + CTRL_DRVPARAM - CP_RAM_BASE, OBJ_PTR)
    struct.pack_into("<IIII", ram, OBJ_PTR + 0x04 - CP_RAM_BASE, B.NMODES, B.T["ids"], 0, REC_BASE)
    return ram


def run_elf_on_ram(elf_info: dict, ram: bytearray, fail_on_write_num: int = None, preexist_result: bool = False):
    mu = Uc(UC_ARCH_ARM64, UC_MODE_ARM)

    # Enable FP/SIMD (CPACR_EL1.FPEN = 0b11)
    mu.reg_write(UC_ARM64_REG_CPACR_EL1, mu.reg_read(UC_ARM64_REG_CPACR_EL1) | (0x3 << 20))

    LOAD_BASE = 0x10000000
    LOAD_SPAN = 0x00100000
    STUB_BASE = 0x20000000
    BUF_VA = 0x30000000
    BUF_PHYS = 0x410000000
    STACK_BASE = 0x40000000
    STACK_SIZE = 0x00100000
    STOP_ADDR = 0x50000000

    mu.mem_map(LOAD_BASE, LOAD_SPAN)
    mu.mem_map(STUB_BASE, 0x1000)
    mu.mem_map(BUF_VA, 0x2000)
    mu.mem_map(STACK_BASE, STACK_SIZE)
    mu.mem_map(STOP_ADDR, 0x1000)

    raw = elf_info["bytes"]
    for pva, pfsz, pmsz, poff, _ in elf_info["loads"]:
        mu.mem_write(LOAD_BASE + pva, raw[poff : poff + pfsz])

    stub_addrs = {
        "_Z9dmm_allocjPj": STUB_BASE + 0x00,
        "_Z8dmm_freej": STUB_BASE + 0x10,
        "sen_dma_transfer": STUB_BASE + 0x20,
    }
    RET_INSN = struct.pack("<I", 0xD65F03C0)
    for va in stub_addrs.values():
        mu.mem_write(va, RET_INSN)

    for r_off, r_type, r_sym, r_add in elf_info["relas"]:
        target_va = LOAD_BASE + r_off
        if r_type == 1027:  # R_AARCH64_RELATIVE
            val = (LOAD_BASE + r_add) & 0xFFFFFFFFFFFFFFFF
            mu.mem_write(target_va, struct.pack("<Q", val))
        elif r_type in (1025, 1026):  # GLOB_DAT / JUMP_SLOT
            nm = elf_info["syms"][r_sym]
            mu.mem_write(target_va, struct.pack("<Q", stub_addrs[nm]))
        else:
            raise AssertionError(f"Unsupported reloc type {r_type}")

    ctor_ptr = struct.unpack("<Q", mu.mem_read(LOAD_BASE + elf_info["init_array_va"], 8))[0]

    state = {
        "handles": {},
        "next_handle": 1,
        "result": bytearray(),
        "out_open": False,
        "mmap_active": False,
        "dma_writes": [],
        "dma_reads": 0,
    }

    def read_cstr_mem(va: int) -> str:
        bs = bytearray()
        while len(bs) < 512:
            b = mu.mem_read(va + len(bs), 1)[0]
            if b == 0:
                break
            bs.append(b)
        return bs.decode("utf8", "replace")

    def hook_alloc(uc, address, size, user_data):
        req_size = uc.reg_read(UC_ARM64_REG_X0)
        h_ptr = uc.reg_read(UC_ARM64_REG_X1)
        assert req_size == 4096, f"unexpected dmm_alloc size {req_size}"
        h = state["next_handle"]
        state["next_handle"] += 1
        state["handles"][h] = True
        uc.mem_write(h_ptr, struct.pack("<I", h))
        uc.reg_write(UC_ARM64_REG_X0, BUF_PHYS)
        uc.reg_write(UC_ARM64_REG_PC, uc.reg_read(UC_ARM64_REG_LR))

    def hook_free(uc, address, size, user_data):
        h = uc.reg_read(UC_ARM64_REG_X0)
        assert state["handles"].get(h) is True, f"invalid or double dmm_free({h})"
        state["handles"][h] = False
        uc.reg_write(UC_ARM64_REG_X0, 0)
        uc.reg_write(UC_ARM64_REG_PC, uc.reg_read(UC_ARM64_REG_LR))

    def hook_dma(uc, address, size, user_data):
        direction = uc.reg_read(UC_ARM64_REG_X0)
        src = uc.reg_read(UC_ARM64_REG_X1)
        dst = uc.reg_read(UC_ARM64_REG_X2)
        n = uc.reg_read(UC_ARM64_REG_X3)
        assert n % 64 == 0 and 0 < n <= 4096, f"illegal DMA size {n}"
        assert direction in (0, 1), f"illegal DMA dir {direction}"

        if direction == 0:
            assert CP_RAM_BASE <= src and src + n <= CP_RAM_BASE + CP_RAM_SIZE, hex(src)
            assert BUF_PHYS <= dst and dst + n <= BUF_PHYS + 4096, hex(dst)
            chunk = bytes(ram[src - CP_RAM_BASE : src - CP_RAM_BASE + n])
            uc.mem_write(BUF_VA + (dst - BUF_PHYS), chunk)
            state["dma_reads"] += 1
            uc.reg_write(UC_ARM64_REG_X0, 0)
        else:
            assert BUF_PHYS <= src and src + n <= BUF_PHYS + 4096, hex(src)
            assert CP_RAM_BASE <= dst and dst + n <= CP_RAM_BASE + CP_RAM_SIZE, hex(dst)
            state["dma_writes"].append((dst, n))
            if fail_on_write_num is not None and len(state["dma_writes"]) == fail_on_write_num:
                uc.reg_write(UC_ARM64_REG_X0, 1)
            else:
                chunk = bytes(uc.mem_read(BUF_VA + (src - BUF_PHYS), n))
                ram[dst - CP_RAM_BASE : dst - CP_RAM_BASE + n] = chunk
                uc.reg_write(UC_ARM64_REG_X0, 0)
        uc.reg_write(UC_ARM64_REG_PC, uc.reg_read(UC_ARM64_REG_LR))

    mu.hook_add(UC_HOOK_CODE, hook_alloc, begin=stub_addrs["_Z9dmm_allocjPj"], end=stub_addrs["_Z9dmm_allocjPj"] + 3)
    mu.hook_add(UC_HOOK_CODE, hook_free, begin=stub_addrs["_Z8dmm_freej"], end=stub_addrs["_Z8dmm_freej"] + 3)
    mu.hook_add(UC_HOOK_CODE, hook_dma, begin=stub_addrs["sen_dma_transfer"], end=stub_addrs["sen_dma_transfer"] + 3)

    def hook_svc(uc, intno, user_data):
        nr = uc.reg_read(UC_ARM64_REG_X8)
        a0 = uc.reg_read(UC_ARM64_REG_X0)
        a1 = uc.reg_read(UC_ARM64_REG_X1)
        a2 = uc.reg_read(UC_ARM64_REG_X2)

        if nr == 56:  # openat(dirfd, path, flags, mode)
            path = read_cstr_mem(a1)
            if path == "/tmp_wbshd/readcheck_result.txt":
                if preexist_result:
                    uc.reg_write(UC_ARM64_REG_X0, (-17) & 0xFFFFFFFFFFFFFFFF)  # -EEXIST
                else:
                    state["out_open"] = True
                    uc.reg_write(UC_ARM64_REG_X0, 10)
            elif path == "/dev/mem":
                assert (a2 & 3) == 2, f"/dev/mem opened with unexpected access mode {a2:#x}"
                uc.reg_write(UC_ARM64_REG_X0, 11)
            elif path.startswith("/proc/") or path.startswith("/sys/"):
                uc.reg_write(UC_ARM64_REG_X0, 12)
            else:
                raise AssertionError(f"Unexpected openat({path!r}, {a2:#x})")
        elif nr == 57:  # close(fd)
            if a0 == 10:
                state["out_open"] = False
            uc.reg_write(UC_ARM64_REG_X0, 0)
        elif nr in (61, 63):  # getdents64 / read on /proc|/sys dummy fd
            uc.reg_write(UC_ARM64_REG_X0, 0)
        elif nr == 64:  # write(fd, buf, count)
            assert a0 == 10 and state["out_open"]
            state["result"].extend(uc.mem_read(a1, a2))
            uc.reg_write(UC_ARM64_REG_X0, a2)
        elif nr == 175:  # geteuid()
            uc.reg_write(UC_ARM64_REG_X0, 0)
        elif nr == 222:  # mmap(addr, len, prot, flags, fd, off)
            fd = uc.reg_read(UC_ARM64_REG_X4)
            off = uc.reg_read(UC_ARM64_REG_X5)
            assert fd == 11 and off == (BUF_PHYS & ~0xFFF) and a1 <= 8192
            state["mmap_active"] = True
            uc.reg_write(UC_ARM64_REG_X0, BUF_VA)
        elif nr == 215:  # munmap(addr, len)
            assert a0 == BUF_VA and state["mmap_active"]
            state["mmap_active"] = False
            uc.reg_write(UC_ARM64_REG_X0, 0)
        else:
            raise AssertionError(f"Unhandled AArch64 syscall {nr}")

    mu.hook_add(UC_HOOK_INTR, hook_svc)

    mu.reg_write(UC_ARM64_REG_SP, STACK_BASE + STACK_SIZE - 0x1000)
    mu.reg_write(UC_ARM64_REG_LR, STOP_ADDR)
    mu.emu_start(ctor_ptr, STOP_ADDR, count=50_000_000)

    assert all(not active for active in state["handles"].values()), "dmm buffer leaked!"
    assert not state["mmap_active"], "mmap leaked!"
    assert not state["out_open"], "result fd leaked!"
    return state["result"].decode("utf8", "replace"), state


def main():
    design = json.loads(DESIGN_JSON.read_text(encoding="utf8"))
    l5_info = parse_and_audit_elf(L5_SO)
    l6_info = parse_and_audit_elf(L6_SO)
    print(f"PASS ELF audit: {L5_SO.name} ({len(l5_info['bytes'])} B) and {L6_SO.name} ({len(l6_info['bytes'])} B)")

    img = B.CPAPP_PATH.read_bytes()
    pal_recs, logs1 = B.run_calc(img, 1)
    ntsc_recs, logs0 = B.run_calc(img, 0)
    assert not logs1 and not logs0

    uninit = {int(o, 16) for o in design["stored_record"]["uninitialized_padding_offsets"]}
    assert len(uninit) == 30
    stock_ram = make_pal_stock_ram(img, pal_recs, uninit)

    rec_addr = int(design["stored_record"]["address"], 16)
    assert rec_addr == REC_BASE + INDEX * REC_SIZE == 0x25DAE04
    rec_offs = [int(o, 16) for o in design["stored_record"]["offsets_that_differ"]]
    assert len(rec_offs) == 64
    expected_new_rec = bytes.fromhex(design["stored_record"]["design"])
    sites = [(int(p["addr"], 16), bytes.fromhex(p["old"]), bytes.fromhex(p["new"])) for p in design["patches"]]
    assert len(sites) == 21

    # Compute exact byte addresses allowed to change
    allowed_addrs = set()
    for a, o, _ in sites:
        for k in range(len(o)):
            allowed_addrs.add(a + k)
    for o in rec_offs:
        allowed_addrs.add(rec_addr + o)

    # Case 1: Fresh Apply (L5_pal25)
    ram1 = bytearray(stock_ram)
    rep1, st1 = run_elf_on_ram(l5_info, ram1)
    assert rep1.startswith("readcheck 1 level 5\n"), rep1[:120]
    assert "DONE: all 22 sites hold the target bytes (apply)" in rep1, rep1[-400:]
    assert "== done, bytes written before this line:" in rep1, rep1[-200:]
    for a, _, new_b in sites:
        assert bytes(ram1[a - CP_RAM_BASE : a - CP_RAM_BASE + len(new_b)]) == new_b, f"site {hex(a)} not updated"
    for o in rec_offs:
        assert ram1[rec_addr - CP_RAM_BASE + o] == expected_new_rec[o], f"rec +{hex(o)} not updated"
    unexpected = [CP_RAM_BASE + i for i in range(CP_RAM_SIZE) if ram1[i] != stock_ram[i] and (CP_RAM_BASE + i) not in allowed_addrs]
    assert not unexpected, f"Unexpected RAM changes outside 22 sites: {[hex(x) for x in unexpected[:10]]}"
    for o in uninit:
        assert ram1[rec_addr - CP_RAM_BASE + o] == 0xAA, f"Padding +{hex(o)} modified!"
    print(f"PASS Case 1: Fresh Apply L5_pal25 ({len(st1['dma_writes'])} DMA writes, 22 sites updated, 0/30 padding & 0 outside bytes touched)")

    # Case 2: Idempotent Re-apply (L5_pal25)
    ram2 = bytearray(ram1)
    rep2, st2 = run_elf_on_ram(l5_info, ram2)
    assert "NOTHING TO DO: every site already holds the target bytes" in rep2, rep2[-400:]
    assert len(st2["dma_writes"]) == 0 and ram2 == ram1
    print("PASS Case 2: Idempotent Re-apply L5_pal25 (NOTHING TO DO, 0 DMA writes)")

    # Case 3: Full Putback (L6_pal25)
    ram3 = bytearray(ram1)
    rep3, st3 = run_elf_on_ram(l6_info, ram3)
    assert rep3.startswith("readcheck 1 level 6\n"), rep3[:120]
    assert "DONE: all 22 sites hold the target bytes (put back)" in rep3, rep3[-400:]
    assert "== done, bytes written before this line:" in rep3, rep3[-200:]
    assert ram3 == stock_ram, "Putback did not restore exact bit-for-bit stock PAL RAM!"
    print(f"PASS Case 3: Full Putback L6_pal25 ({len(st3['dma_writes'])} DMA writes, bit-for-bit stock PAL RAM restored)")

    # Case 4: Safety refusal on NTSC (hz=0) stored record
    ram4_stock = make_pal_stock_ram(img, pal_recs, uninit, ntsc_mode_820=ntsc_recs[MODE][1])
    ram4 = bytearray(ram4_stock)
    rep4, st4 = run_elf_on_ram(l5_info, ram4)
    assert "nothing is written" in rep4, rep4[-400:]
    assert len(st4["dma_writes"]) == 0 and ram4 == ram4_stock
    print("PASS Case 4: Refuses NTSC (hz=0) stored record cleanly (0 DMA writes, RAM untouched)")

    # Case 5: Safety refusal on 1-byte mismatch in sensor cell 0xdcdd50
    ram5_stock = bytearray(stock_ram)
    ram5_stock[0xDCDD50 - CP_RAM_BASE] ^= 0x01
    ram5 = bytearray(ram5_stock)
    rep5, st5 = run_elf_on_ram(l5_info, ram5)
    assert "nothing is written" in rep5, rep5[-400:]
    assert len(st5["dma_writes"]) == 0 and ram5 == ram5_stock
    print("PASS Case 5: Refuses 1-byte sensor cell mismatch cleanly (0 DMA writes, RAM untouched)")

    # Case 6: Mid-apply rollback/undo on 10th write failure
    ram6 = bytearray(stock_ram)
    rep6, st6 = run_elf_on_ram(l5_info, ram6, fail_on_write_num=10)
    assert "undo: every site this run touched gets its earlier bytes back" in rep6, rep6[-500:]
    assert "NOT DONE: a step failed; every site this run touched was put back" in rep6, rep6[-300:]
    assert ram6 == stock_ram, "Rollback left dirty bytes in coprocessor RAM!"
    print(f"PASS Case 6: Mid-apply 10th-write failure triggers clean undo ({len(st6['dma_writes'])} writes incl undo, bit-for-bit stock PAL RAM restored)")


if __name__ == "__main__":
    main()
