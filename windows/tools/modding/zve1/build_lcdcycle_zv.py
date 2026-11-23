r"""Design lcdcycle_zv_v1: the A7C II port's C2 preview cycle (lcdcycle_c2_v1, itself the A7 IV's lcdcycle_v6, which works on that camera:
F858, F969) for the ZV-E1 2.02 (zve1_202), with the 2.25:1 state of the A7S III's lcdcycle_s3_v3. In movie mode C2 steps the rear-screen
preview 3:2 -> 2:1 (1.33x) -> 2.25:1 (1.5x) -> 2.4:1 (1.6x) -> 3:2 and keeps the focus frames. Notes: modding/ZVE1_PORT_LCDCYCLE.md.

The ZV-E1 has two custom buttons (Help Guide 2310: C1 on top, "Background Defocus"; C2 on the rear, "Step zoom"). The trigger is the raw C2
press EVENT_INPUT_KEY_TACT_CUSTOM2_ON 0x2150003 (as the A7C II port); the C3 press 0x2150006 is accepted too (this body has no C3 key). The rear
panel is 3:2 (720x480) and there is no viewfinder, so the A7 IV logic is kept: the fit word of a 16:9 picture on a panel of code 1, and row 1 of
the frame tables.

Where the pieces are in the 2.02 files (build/lcdcycle_c2/find_pieces.py zve1_202, byte search; each is asserted below):
  hook      0x1f7c61c presenter_controller_manager::process_input_event, `sub sp, sp, #0x480`; the event code at event+8 (`ldr w1, [x24, #8]`
            at 0x1f7c770, x24 = x1), as on the A7 IV and A7C II
  calls     dlsym .plt 0x17de7c0 (stub of the JUMP_SLOT of `dlsym`, GOT 0x567dba0); system-mode accessor 0x28a6740 (field +0xced0; A7C II
            +0xcf50, A7 IV +0xd798: 26 of 29 votes by call position in 24 same-named callers); vdf_set_yuv_layout wrapper 0x33a3558 (the A7 IV
            wrapper's code, lock id 0x21, calls detail::vdf_set_yuv_layout 0x33cd25c whose case 0 is the A7 IV's)
  cave      the page 0x17d6000-0x17d7000 inside .rela.dyn (DT_RELA 0xf3e0, DT_RELASZ 0x17c8d70, ends at DT_JMPREL 0x17d8150), R_AARCH64_ABS64
            entries only, as the A7C II port. The first segment's tail (0x4afa880..0x4afb000, 1920 bytes) is NOT zero on this build: the file's
            next segment starts inside that page, so it is not used.
  lines     build/lcdcycle_zv/pool.h, generated here from the 2.02 coprocessor image: the fit word 0x1f5c88, the constants 0x1f5e90 and
            0x1f5e94, the two frame-table entries 0xe9b420 (AF window, loaded at 0x128644) and 0xe9b498 (tracking, 0x1295ca). The A7C II's
            third table (the remote-send variant of the AF window, 0xec4388) has no counterpart on the ZV-E1.

Unicorn: the stub and lcd_step run on the stock appFw bytes with Python stand-ins for dlsym, the three libsencore functions, the system
calls, the mode accessor and the layout call, against a model of the four coprocessor lines.

  work\venv\Scripts\python.exe -I -B build/build_lcdcycle_zv.py   writes build/lcdcycle_zv/pool.h, modding/designs/lcdcycle_zv_v1.json
                                                                  and evidence/zve1/lcdcycle_zv_v1_emu.json
"""
import hashlib
import io
import json
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

import capstone
import keystone
import unicorn as U
import unicorn.arm64_const as A

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "build"))
import locate_file  # noqa: E402

BUILD = "zve1_202"
SRC = ROOT / "build/lcdcycle_zv/step.c"
ZIG = [str(ROOT / "work/venv_zig/Scripts/python.exe"), "-m", "ziglang"]
B = 0x108000
HOOK1, HOOK1_OLD = 0x1F7C61C, "sub sp, sp, #0x480"
BACK1 = HOOK1 + 4
CAVE, CAVE_END = 0x17D6000, 0x17D7000                    # one page of .rela.dyn (R_AARCH64_ABS64 entries only)
SYMS = {"appfw_dlsym": 0x17DE7C0, "appfw_system_mode": 0x28A6740, "appfw_vdf_layout": 0x33A3558}
A7IV = {"hook": 0x1F06594, "appfw_dlsym": 0x17166A0, "appfw_system_mode": 0x28ECDF8, "appfw_vdf_layout": 0x35994DC}
VDF_DETAIL = 0x33CD25C                                   # infra_wrapper_bb::detail::vdf_set_yuv_layout (A7 IV 0x35bff9c, A7C II 0x34f132c)
TRIGGERS = (0x2150003, 0x2150006)                        # C2 (this body's rear "Step zoom" key), C3 (A7 IV's key; never sent here)
NOOP = 0x20F00BC                                         # EVENT_FUNC_CUSTOM_NOT_SET_ON (0x20f00be on the A7 IV and A7C II)
EVENT_RECORDS = {0x2150000: (0x5162808, "EVENT_INPUT_KEY_TACT_CUSTOM_ON"), 0x2150003: (0x5162838, "EVENT_INPUT_KEY_TACT_CUSTOM2_ON"),
                 0x2150006: (0x5162868, "EVENT_INPUT_KEY_TACT_CUSTOM3_ON"), 0x20F00BC: (0x5161E98, "EVENT_FUNC_CUSTOM_NOT_SET_ON")}
STEP_AT = CAVE + 0x60
rect = lambda r: struct.unpack("<2I", struct.pack("<4H", *r))
RECT_T = [(0, 0, 640, 480), (0, 60, 640, 360), (0, 80, 640, 320), (0, 90, 640, 300), (0, 38, 640, 404)]   # 3:2, 2:1, 2.25:1, 2.4:1, stock
NS = 4                                                   # states in the cycle
RECTS = [rect(r) for r in RECT_T]
BWORDS = [(0x0E09F04F, 0x2010BF08), (0x0E01F04F, 0x2002BF08), (0x0E04F04F, 0x2009BF08), (0x0E05F04F, 0x200CBF08)]   # moveq.w lr,#n ; it eq ;
#                                                        moveq r0,#d : 9/16 (3:2 with the fill word), 1/2, 4/9 (lcdcycle_s3_v3's), 5/12
FITS = (0, 3, 3, 3)                                      # the fit word of each state: 0 = fill (lcdfill), 3 = letterbox
FIT, CONST, ENTRIES = 0x1F5C88, 0x1F5E90, (0xE9B420, 0xE9B498)
TABLES = (0xE9B3E0, 0xE9B458)                            # A7 IV 0xd7b560, 0xd7b650 (AF window, tracking); no remote-send variant on this body
FIT_FN, RATIO_FN = 0x1F5C34, 0x1F5E5C                    # A7 IV 0x1e4b78 (identical); A7S III 0x1e4f64 (identical)
WIDGET_LOADS = (0x128644, 0x1295CA)                      # A7C II 0x128558, 0x129992 (match_seed 92 / 111 votes)
# name, address of the first site word, guards (word index from it), candidates, the candidate the stock image holds
LINES = [("A", FIT, (-2, -1, 1, 2), [(f,) for f in FITS], 1),    # the fit word is the third word of its line here: guards -2, -1 (`bx lr; nop`,
         #                                                            the value 3 before it), +1, +2 (the table words after it)
         ("B", CONST, (-1, 2, 3), BWORDS, 0),                       # guards as in the A7S III and A7C II ports: the instructions around the constants
         ("T0", ENTRIES[0], (-2, -1, 2, 3), RECTS, 4),              # guards as in v6: the 1:1 entry before, the fifth aspect after
         ("T1", ENTRIES[1], (-2, -1, 2, 3), RECTS, 4)]
CP = locate_file.locate(BUILD, "cpapp-b.bin").read_bytes()
CP4 = locate_file.locate("a7iv_602", "cpapp-b.bin").read_bytes()
CP3 = locate_file.locate("a7s3_501", "cpapp-b.bin").read_bytes()
u32 = lambda a: struct.unpack_from("<I", CP, a - B)[0]
line_of = lambda a: a & ~63
MD = capstone.Cs(capstone.CS_ARCH_ARM64, capstone.CS_MODE_ARM)


def pool():
    """The POOL words and DESC rows of step.c, from the 2.02 image. Equal runs of words are stored once."""
    words, rows, at = [], [], {}

    def put(seq):
        seq = tuple(seq)
        if seq not in at:
            at[seq] = len(words)
            words.extend(seq)
        return at[seq]

    for name, addr, guards, cands, stock in LINES:
        base, nw = (addr - line_of(addr)) // 4, len(cands[0])
        assert addr % 4 == 0 and base + nw <= 16 and all(0 <= base + g < 16 and not 0 <= g < nw for g in guards), name
        assert tuple(u32(addr + 4 * i) for i in range(nw)) == cands[stock], "%s: the stock image does not hold candidate %d" % (name, stock)
        g_at = put(x for g in guards for x in (g & 0xFFFFFFFF, u32(addr + 4 * g)))
        c_at = put(x for cnd in cands for x in cnd)
        rows.append((name, line_of(addr), base, len(guards), len(cands), nw, g_at, c_at))
    assert len(words) < 256
    return words, rows


def pool_h(words, rows):
    out = ["/* Generated by build/build_lcdcycle_zv.py from cpapp-b.bin 2.02 (ZV-E1). Do not edit. */",
           "/* Guards are {word index from the first site word, value} pairs; candidates follow in the order 3:2, 2:1, 2.25:1, 2.4:1 (and stock, tables). */",
           "static const u32 POOL[] = {"]
    for k in range(0, len(words), 8):
        out.append("    " + ", ".join("0x%08xu" % w for w in words[k:k + 8]) + ",     /* %d */" % k)
    out += ["};", "static const struct desc DESC[%d] = {" % len(rows)]
    for name, line, base, ng, ncand, nw, g, c in rows:
        out.append("    { 0x%x, %d, %d, %d, %d, %d, %d },      /* %s: first site word 0x%x */" % (line, base, ng, ncand, nw, g, c, name, line + 4 * base))
    names = [r[0] for r in rows]
    out += ["};", "enum { D_A = %d, D_B = %d, D_T0 = %d, D_TLAST = %d };" % (names.index("A"), names.index("B"), names.index("T0"), len(rows) - 1)]
    return "\n".join(out) + "\n"


def stub_asm(step):
    c2, c3 = TRIGGERS
    return f"""
    ldr w16, [x1, #8]
    movz w17, #{c2 & 0xFFFF}
    movk w17, #{c2 >> 16}, lsl #16
    cmp w16, w17
    b.eq s_take
    movz w17, #{c3 & 0xFFFF}
    movk w17, #{c3 >> 16}, lsl #16
    cmp w16, w17
    b.ne s_out
s_take:
    stp x29, x30, [sp, #-64]!
    mov x29, sp
    stp x0, x1, [sp, #16]
    stp x2, x3, [sp, #32]
    bl {step:#x}
    mov w16, w0
    ldp x2, x3, [sp, #32]
    ldp x0, x1, [sp, #16]
    cbz w16, s_pop
    movz w17, #{NOOP & 0xFFFF}
    movk w17, #{NOOP >> 16}, lsl #16
    str w17, [x1, #8]
s_pop:
    ldp x29, x30, [sp], #64
s_out:
    sub sp, sp, #0x480
    b {BACK1:#x}
"""


def compile_step():
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        (td / "link.ld").write_text("".join("%s = %#x;\n" % kv for kv in SYMS.items())
                                    + "ENTRY(lcd_step)\nSECTIONS {\n  . = %#x;\n  .text : { *(.text.lcd_step) *(.text*) *(.rodata*) }\n"
                                    "  /DISCARD/ : { *(.comment) *(.note*) *(.eh_frame*) *(.data*) *(.bss*) *(.got*) }\n}\n" % STEP_AT, encoding="ascii")
        elf, obj = td / "step.elf", td / "step.o"
        cflags = ["-target", "aarch64-linux-gnu", "-Oz", "-ffreestanding", "-fno-builtin", "-fno-stack-protector", "-fPIE", "-fno-plt",
                  "-ffixed-x18", "-mgeneral-regs-only", "-fno-asynchronous-unwind-tables", "-ffunction-sections", "-Wall", "-Wextra", "-Werror"]
        subprocess.run(ZIG + ["cc"] + cflags + ["-c", str(SRC), "-o", str(obj)], check=True)
        subprocess.run(ZIG + ["cc", "-target", "aarch64-linux-gnu", "-nostdlib", "-static", "-Wl,-T," + str(td / "link.ld")] + [str(obj), "-o", str(elf)], check=True)
        from elftools.elf.elffile import ELFFile
        e = ELFFile(io.BytesIO(elf.read_bytes()))
        text = e.get_section_by_name(".text")
        assert text["sh_addr"] == STEP_AT
        assert not [s.name for s in e.iter_sections() if s.name.startswith(".rela") or s.name in (".got", ".data", ".bss", ".dynamic")], "the routine must have no data or relocations"
        sym = {s.name: s["st_value"] for s in e.get_section_by_name(".symtab").iter_symbols()}
        assert sym["lcd_step"] == STEP_AT
        return text.data()


def build():
    ks = keystone.Ks(keystone.KS_ARCH_ARM64, keystone.KS_MODE_LITTLE_ENDIAN)
    stub = bytes(ks.asm(stub_asm(STEP_AT), CAVE)[0])
    assert len(stub) <= STEP_AT - CAVE
    step = compile_step()
    code = stub.ljust(STEP_AT - CAVE, b"\0") + step
    assert CAVE + len(code) <= CAVE_END, "the routine is %d bytes, %d available" % (len(code), CAVE_END - CAVE)
    hook = bytes(ks.asm("b %#x" % CAVE, HOOK1)[0])
    old = bytes(ks.asm(HOOK1_OLD, HOOK1)[0])
    return code, stub, step, old, hook


# ---------------------------------------------------------------------------------------------------------------- checks of the 2.02 files
def dis(img, a, n):
    return [("%s %s" % (i.mnemonic, i.op_str)).strip() for i in MD.disasm(img[a:a + 4 * n], a)]


def masked(img, a, n):
    return [i.mnemonic + " " + ("T" if i.mnemonic in ("b", "bl") else i.op_str) for i in MD.disasm(img[a:a + 4 * n], a)]


def elf_facts(img):
    from elftools.elf.elffile import ELFFile
    e = ELFFile(io.BytesIO(img))
    load = [s for s in e.iter_segments() if s["p_type"] == "PT_LOAD"]
    dyn = {t.entry.d_tag: t.entry.d_val for t in e.get_section_by_name(".dynamic").iter_tags()}
    dynsym, rela, plt = e.get_section_by_name(".dynsym"), e.get_section_by_name(".rela.plt"), e.get_section_by_name(".plt")
    got = [r["r_offset"] for r in rela.iter_relocations() if dynsym.get_symbol(r["r_info_sym"]).name == "dlsym"]
    return load, dyn, got, (plt["sh_addr"], plt["sh_size"])


def check_files(img, img4):
    """Assert every appFw.so and cpapp-b.bin fact the design relies on. Returns notes for the design record."""
    facts = {}
    # the hook: process_input_event's first instruction, the 0x178-byte copy of the event from x1, the event code at +8
    sub480 = bytes(keystone.Ks(keystone.KS_ARCH_ARM64, keystone.KS_MODE_LITTLE_ENDIAN).asm(HOOK1_OLD, HOOK1)[0])
    assert img[HOOK1:HOOK1 + 4] == img4[A7IV["hook"]:A7IV["hook"] + 4] == sub480, "the hooked instruction is not `sub sp, sp, #0x480`"
    want = ["sub sp, sp, #0x480", "stp x29, x30, [sp, #-0x60]!", "mov x29, sp", "stp x19, x20, [sp, #0x10]", "add x20, x29, #0x1f0",
            "stp x27, x28, [sp, #0x50]", "mov x27, x0", "mov x0, x20", "stp x21, x22, [sp, #0x20]", "uxtb w21, w2", "mov x2, #0x178",
            "stp x23, x24, [sp, #0x30]", "mov x24, x1", "stp x25, x26, [sp, #0x40]", "uxtb w25, w3", "str xzr, [x29, #0x1e8]"]
    assert dis(img, HOOK1, 16) == want, "process_input_event does not start as expected"
    assert dis(img, HOOK1 + 0x44, 1) == ["ldr w0, [x29, #0x1f0]"] and dis(img, HOOK1 + 0x154, 2) == ["ldr w1, [x24, #8]", "ldr w0, [x29, #0x1f8]"], "the event code is not at +8"
    # the pretty-function string of the hooked function's source (the function's name in the index comes from it)
    assert b"presenter_controller_manager::process_input_event(const ds_event&, bool, bool)" in img
    # dlsym: the .plt stub of the JUMP_SLOT relocation of `dlsym`
    load, dyn, got, (plt0, pltn) = elf_facts(img)
    assert len(got) == 1
    p = SYMS["appfw_dlsym"]
    ins = list(MD.disasm(img[p:p + 16], p))
    page, lo = int(ins[0].op_str.split("#")[1], 16), int(ins[1].op_str.split("#")[1].rstrip("]"), 16)
    assert plt0 <= p < plt0 + pltn and ins[0].mnemonic == "adrp" and ins[1].mnemonic == "ldr" and ins[3].op_str == "x17" and page + lo == got[0], "not the .plt stub of dlsym"
    facts["dlsym_got"] = hex(got[0])
    # the system-mode accessor: the A7 IV's code with another field offset (26 of 29 votes by call position, find_pieces.py); called in
    # master_input_eventgp_fn_play_screen_screengp_other_controller::process_EVENT_INPUT_TACT_PL... (zv 0x1c452c4, call 0x1c452ec; A7 IV call
    # 0x1ba6104), the value read with `ldr w20, [x0]` in both. (The A7C II port's call site, mp_remote_send_decider, is not in this build.)
    m = SYMS["appfw_system_mode"]
    acc = dis(img, m, 5)
    assert acc[0].startswith("adrp x0, #") and acc[1] == "mov x1, #0xced0" and acc[2].startswith("add x0, x0, #") and acc[3:] == ["add x0, x0, x1", "ret"], acc
    assert masked(img4, A7IV["appfw_system_mode"], 5)[3:] == ["add x0, x0, x1", "ret "] and dis(img4, A7IV["appfw_system_mode"], 2)[1] == "mov x1, #0xd798"
    assert dis(img, 0x1C452EC, 2) == ["bl #0x28a6740", "ldr w20, [x0]"] and dis(img4, 0x1BA6104, 2) == ["bl #0x28ecdf8", "ldr w20, [x0]"]
    facts["system_mode_field"] = "+0xced0 (A7C II +0xcf50, A7 IV +0xd798)"
    # the layout wrapper: the A7 IV wrapper's 16 instructions with branch targets masked, lock id 0x21, calling detail::vdf_set_yuv_layout
    w = SYMS["appfw_vdf_layout"]
    assert masked(img, w, 16) == masked(img4, A7IV["appfw_vdf_layout"], 16) and dis(img, w, 7)[6] == "mov w1, #0x21"
    assert dis(img, w + 0x28, 1) == ["bl #%#x" % VDF_DETAIL]
    assert b"void infra_wrapper_bb::detail::vdf_set_yuv_layout(const infra_wrapper_bb::vdf_set_yuv_layout_in_t&, infra_wrapper_bb::vdf_set_yuv_layout_out_t&)" in img
    # its case 0 (in[0] == 0): the switch on in[0] through a table of u16 offsets, case 0 fills the fixed 640x480 layout message and sends
    # command 0x92840747 as the A7 IV's does (A7 IV case 0 at 0x35c06c8; the frame offsets differ by 0x20)
    assert dis(img, VDF_DETAIL + 0x30, 1) == ["ldr w2, [x19]"] and dis(img, VDF_DETAIL + 0x40, 1) == ["cmp w2, #3"]
    assert dis(img, VDF_DETAIL + 0x48, 1) == ["mov w0, #0x14c"]                            # the message header word, as the A7S III and A7C II
    # the switch: adrp/add x1 = 0x467b25c (u16 offsets), base 0x33cd2dc
    assert dis(img, 0x33CD2C0, 7) == ["adrp x1, #0x467b000", "mov w0, #1", "add x1, x1, #0x25c", "ldrh w1, [x1, w2, uxtw #1]", "adr x2, #0x33cd2dc",
                                      "add x1, x2, w1, sxth #2", "br x1"]
    case0 = 0x33CD2DC + 4 * struct.unpack_from("<h", img, 0x467B25C)[0]
    assert case0 == 0x33CDAB4 and dis(img, case0, 11) == ["strb w0, [x29, #0x91]", "mov w1, #7", "strb w0, [x29, #0x92]", "mov w0, #0x280", "strb w1, [x29, #0x90]",
                                                          "strh w0, [x29, #0x98]", "mov w0, #0x1e0", "strh w0, [x29, #0x9a]", "mov w0, #3",
                                                          "strb w0, [x29, #0xa8]", "b #0x33cd5e0"]
    # the common tail: in[0] == 0 skips to the send of command 0x92840747
    assert dis(img, 0x33CD5E0, 3) == ["ldr w0, [x19]", "add x20, x29, #0x78", "cbz w0, #0x33cd618"]
    assert dis(img, 0x33CD620, 1) == ["mov w0, #0x747"] and dis(img, 0x33CD62C, 1) == ["movk w0, #0x9284, lsl #16"]
    # the event ids: name records {u32 id, u32 length with NUL, u64 name}
    for ev, (va, name) in EVENT_RECORDS.items():
        off = va - 0x10000                                   # second segment: file offset = address - 0x10000
        i, n, s = struct.unpack_from("<IIQ", img, off)
        assert (i, n) == (ev, len(name) + 1) and img[s:s + n] == name.encode() + b"\0", name
    # the cave: one page of .rela.dyn, inside the first (r-x) segment, before the lazily bound .rela.plt; no text relocations
    seg0 = load[0]
    assert seg0["p_offset"] == 0 and seg0["p_vaddr"] == 0 and seg0["p_flags"] == 5 and CAVE_END <= seg0["p_filesz"]
    assert dyn["DT_RELA"] <= CAVE and CAVE_END <= dyn["DT_RELA"] + dyn["DT_RELASZ"] <= dyn["DT_JMPREL"] and dyn["DT_RELAENT"] == 24
    assert "DT_TEXTREL" not in dyn and not (dyn.get("DT_FLAGS", 0) & 4), "text relocations: the loader would write the text segment"
    end0 = seg0["p_filesz"]
    facts["first_segment_end"], facts["tail_cave_bytes"] = hex(end0), ((end0 + 0xFFF) & ~0xFFF) - ((end0 + 15) & ~15)
    # the tail of the first segment's last page is NOT zero on this build: the second segment's file bytes start inside that page
    seg1 = load[1]
    assert facts["tail_cave_bytes"] == 1920 and seg1["p_offset"] < ((end0 + 0xFFF) & ~0xFFF) and any(img[end0:(end0 + 0xFFF) & ~0xFFF])
    facts["tail_note"] = "not used: the second segment's file data starts at %#x, inside the first segment's last page" % seg1["p_offset"]
    facts["rela_dyn"] = {"DT_RELA": hex(dyn["DT_RELA"]), "DT_RELASZ": hex(dyn["DT_RELASZ"]), "DT_JMPREL": hex(dyn["DT_JMPREL"]), "DT_RELACOUNT": hex(dyn.get("DT_RELACOUNT", 0))}
    types = {struct.unpack_from("<Q", img, a + 8)[0] & 0xFFFFFFFF for a in range(dyn["DT_RELA"] + (CAVE - dyn["DT_RELA"]) // 24 * 24, CAVE_END, 24)}
    assert types <= {257, 1025, 1027}, types                 # R_AARCH64_ABS64, GLOB_DAT, RELATIVE: all applied at load
    facts["relocation_types_in_cave"] = sorted(types)
    # the hook branch and every call reach
    assert abs(CAVE - HOOK1) < 1 << 27 and all(abs(v - CAVE) < 1 << 27 for v in SYMS.values())
    # coprocessor: the fit-mode function and its three tables are the A7 IV's (0x94 bytes, unique); the picture-ratio function is the A7S III's
    assert CP[FIT_FN - B:FIT_FN - B + 0x94] == CP4[0x1E4B78 - B:0x1E4B78 - B + 0x94] and CP.count(CP[FIT_FN - B:FIT_FN - B + 0x94]) == 1
    assert FIT - FIT_FN == 0x1E4BCC - 0x1E4B78 and u32(FIT) == 3
    assert CP[RATIO_FN - B:RATIO_FN - B + 0x114] == CP3[0x1E4F64 - B:0x1E4F64 - B + 0x114], "the picture-ratio function is not the A7S III's"
    assert CONST - RATIO_FN == 0x1E4F98 - 0x1E4F64 and (u32(CONST), u32(CONST + 4)) == BWORDS[0]
    assert CP.count(bytes.fromhex("4ff0870e4ff48070")) == 1 and CP.find(bytes.fromhex("4ff0870e4ff48070")) + B == RATIO_FN + 0x46     # its 2.35:1 case, once
    for t, u, e in zip(TABLES, (0xD7B560, 0xD7B650), ENTRIES):
        assert CP[t - B:t - B + 0x78] == CP4[u - B:u - B + 0x78] and e == t + 0x40 and struct.unpack_from("<4H", CP, e - B) == RECT_T[4]
    assert all(CP.count(CP[t - B:t - B + 0x78]) == 2 for t in TABLES)        # the two tables are equal and nowhere else (the A7C II has three)
    # the frame widgets load the two tables (MOVW/MOVT of each table's address); the code that loads them is the A7C II's AF-window and
    # tracking widgets (match_seed: 0x128500 -> +0xec, 92 votes; 0x129940 -> -0x3c8, 111 votes); the A7C II's remote-send variant (0x128e4e) has
    # no counterpart here, and no other code builds a table address
    for at, t in zip(WIDGET_LOADS, TABLES):
        mw = [i for i in capstone.Cs(capstone.CS_ARCH_ARM, capstone.CS_MODE_THUMB).disasm(CP[at - B:at - B + 12], at)]
        assert mw[0].mnemonic == "movw" and int(mw[0].op_str.split("#")[1], 16) == t & 0xFFFF and any(i.mnemonic == "movt" and int(i.op_str.split("#")[1], 16) == t >> 16 for i in mw)
    import find_movw
    assert sorted(c for v, c, _ in find_movw.pairs(CP, TABLES[0], TABLES[1] + 0x78)) == list(WIDGET_LOADS)
    facts["frame_widget_table_loads"] = [hex(a) for a in WIDGET_LOADS]
    return facts


# ---------------------------------------------------------------------------------------------------------------------------- emulation
class Emu:
    MAPVA = 0x62000000

    def __init__(self, img, code, cp, sysmode, fail=None):
        self.mu = mu = U.Uc(U.UC_ARCH_ARM64, U.UC_MODE_ARM)
        for a in sorted({HOOK1 & ~0xFFF, CAVE & ~0xFFF} | {v & ~0xFFF for v in SYMS.values()}):     # only the pages the test touches
            mu.mem_map(a, 0x1000)
            mu.mem_write(a, img[a:a + 0x1000])
        mu.mem_write(CAVE, code)
        mu.mem_map(0x60000000, 0x10000)                       # the model's system mode
        mu.mem_write(0x60000000, struct.pack("<I", sysmode))
        mu.mem_map(0x61000000, 0x1000)
        mu.mem_map(self.MAPVA, 0x2000)
        mu.mem_map(0x70000000, 0x100000)
        self.cp = {k: bytearray(v) for k, v in cp.items()}
        self.phys, self.calls, self.fail, self.fds, self.maps = 0x4C0001000, [], fail or {}, set(), []
        mu.hook_add(U.UC_HOOK_CODE, self.code_hook)
        mu.hook_add(U.UC_HOOK_INTR, self.svc)

    def r(self, n):
        return self.mu.reg_read(getattr(A, "UC_ARM64_REG_X%d" % n))

    def ret(self, v=None):
        if v is not None:
            self.mu.reg_write(A.UC_ARM64_REG_X0, v & 0xFFFFFFFFFFFFFFFF)
        self.mu.reg_write(A.UC_ARM64_REG_PC, self.r(30))

    def cstr(self, a):
        b = bytes(self.mu.mem_read(a, 64))
        return b[:b.index(0)].decode()

    def code_hook(self, mu, addr, size, _):
        if addr == SYMS["appfw_dlsym"]:
            name = self.cstr(self.r(1))
            want = {"_Z9dmm_allocjPj": 0x61000000, "_Z8dmm_freej": 0x61000010, "sen_dma_transfer": 0x61000020}
            self.calls.append(("dlsym", self.r(0), name))
            self.ret(0 if self.fail.get("dlsym") == name else want.get(name, 0))
        elif addr == SYMS["appfw_system_mode"]:
            self.calls.append(("mode",))
            self.ret(0x60000000)
        elif addr == SYMS["appfw_vdf_layout"]:
            self.calls.append(("layout", bytes(mu.mem_read(self.r(0), 48)), bytes(mu.mem_read(self.r(1), 16))))
            self.ret()
        elif addr == 0x61000000:
            self.calls.append(("alloc", self.r(0)))
            mu.mem_write(self.r(1), struct.pack("<I", 0x77))
            self.ret(0 if self.fail.get("alloc") else self.phys)
        elif addr == 0x61000010:
            self.calls.append(("free", self.r(0)))
            self.ret(0)
        elif addr == 0x61000020:
            d, src, dst, n = self.r(0) & 0xFFFFFFFF, self.r(1), self.r(2), self.r(3) & 0xFFFFFFFF
            self.calls.append(("xfer", d, src, dst, n))
            if self.fail.get("xfer") == (d, src if d == 0 else dst):
                return self.ret(1)
            va = lambda phys: self.MAPVA + (phys & 0xFFF)
            if d == 0:
                assert dst == self.phys and n == 64 and src in self.cp, "a read that is not one listed 64-byte line: %#x" % src
                if not self.fail.get("noread"):
                    mu.mem_write(va(dst), bytes(self.cp[src]))
            else:
                assert src == self.phys and n == 64 and dst in self.cp, "a write that is not one listed 64-byte line: %#x" % dst
                if not self.fail.get("lost"):
                    self.cp[dst][:] = bytes(mu.mem_read(va(src), 64))
            self.ret(0)

    def svc(self, mu, intno, _):
        n = self.r(8)
        if n == 56:
            self.calls.append(("openat", self.cstr(self.r(1)), hex(self.r(2))))
            self.fds.add(9)
            mu.reg_write(A.UC_ARM64_REG_X0, 9)
        elif n == 222:
            self.calls.append(("mmap", self.r(1), self.r(2), self.r(3), self.r(4), self.r(5)))
            assert self.r(5) == self.phys & ~0xFFF and self.r(4) == 9
            self.maps.append(self.MAPVA)
            mu.reg_write(A.UC_ARM64_REG_X0, self.MAPVA)
        elif n == 215:
            self.calls.append(("munmap", self.r(0)))
            self.maps.remove(self.r(0))
            mu.reg_write(A.UC_ARM64_REG_X0, 0)
        elif n == 57:
            self.calls.append(("close", self.r(0)))
            self.fds.discard(self.r(0))
            mu.reg_write(A.UC_ARM64_REG_X0, 0)
        else:
            raise AssertionError("unexpected system call %d" % n)

    def press(self, event=TRIGGERS[0]):
        mu = self.mu
        sp, ev = 0x70080000, 0x70010000
        mu.mem_write(ev, struct.pack("<III", 0, 0, event))
        regs = {0: 0x1111, 1: ev, 2: 0x2222, 3: 0x3333, 19: 0x1919, 20: 0x2020, 21: 0x2121, 22: 0x2222, 23: 0x2323, 24: 0x2424, 25: 0x2525,
                26: 0x2626, 27: 0x2727, 28: 0x2828, 29: 0x2929, 30: 0x3030}
        for k, v in regs.items():
            mu.reg_write(getattr(A, "UC_ARM64_REG_X%d" % k), v)
        mu.reg_write(A.UC_ARM64_REG_SP, sp)
        mu.emu_start(HOOK1, BACK1, count=40000)
        got = {k: self.r(k) for k in regs}
        return (mu.reg_read(A.UC_ARM64_REG_PC) == BACK1 and mu.reg_read(A.UC_ARM64_REG_SP) == sp - 0x480 and got == regs,
                struct.unpack("<I", mu.mem_read(ev + 8, 4))[0])

    def word(self, addr):
        return struct.unpack_from("<I", self.cp[line_of(addr)], addr - line_of(addr))[0]

    def picture(self):
        """Index of the preview state the picture words are in (fit word and constants agree), or the raw words."""
        w = (self.word(FIT), self.word(CONST), self.word(CONST + 4))
        for k in range(NS):
            if w == (FITS[k],) + BWORDS[k]:
                return k
        return w

    def entries(self):
        return [(self.word(a), self.word(a + 4)) for a in ENTRIES]

    def n(self, kind, direction=None):
        return sum(1 for c in self.calls if c[0] == kind and (direction is None or c[1] == direction))


SITE_WORDS = {a + 4 * i for _, a, _, cands, _ in LINES for i in range(len(cands[0]))}


def cp_model(fit=0, bstate=0, rects=(0, 0)):
    """The four coprocessor lines from the 2.02 image with the fit word, the constants and the two table entries set."""
    cp = {line_of(a): bytearray(CP[line_of(a) - B:line_of(a) - B + 64]) for _, a, _, _, _ in LINES}
    put = lambda a, v: struct.pack_into("<I", cp[line_of(a)], a - line_of(a), v)
    put(FIT, fit)
    put(CONST, BWORDS[bstate][0]), put(CONST + 4, BWORDS[bstate][1])
    for a, k in zip(ENTRIES, rects):
        put(a, RECTS[k][0]), put(a + 4, RECTS[k][1])
    return cp


def rest_same(e):
    """Every byte of the four lines that is not a site word still holds the image's value."""
    for line, b in e.cp.items():
        for off in range(0, 64, 4):
            if line + off not in SITE_WORDS and bytes(b[off:off + 4]) != CP[line + off - B:line + off - B + 4]:
                return False
    return True


def tests(img, code, hook):
    out, fails = [], []
    NT, STOCK = len(ENTRIES), len(RECTS) - 1

    def case(label, cond, detail=None):
        out.append({"case": label, "ok": bool(cond), **({"detail": detail} if detail else {})})
        if not cond:
            fails.append(label)

    img = bytearray(img)
    img[HOOK1:HOOK1 + 4] = hook
    img = bytes(img)
    new = lambda cp=None, mode=3, fail=None: Emu(img, code, cp or cp_model(), mode, fail)
    released = lambda f: not f.maps and not f.fds and f.n("alloc") == f.n("free")
    C2, C3 = TRIGGERS
    all_rects = lambda k: [RECTS[k]] * NT

    e = new()                                                 # the lcdfill state: fit 0, tables whole panel
    seq = []
    for k in range(NS + 1):
        okregs, ev = e.press()
        seq.append((okregs, hex(ev), e.picture(), e.entries(), e.n("layout"), rest_same(e)))
    case("five C2 presses in movie mode step 3:2 -> 2:1 -> 2.25:1 -> 2.4:1 -> 3:2 -> 2:1: fit word and constants as designed, one layout call each, event swallowed",
         all(s[0] and s[1] == hex(NOOP) and s[2] == (k + 1) % NS and s[4] == k + 1 for k, s in enumerate(seq)), [list(map(str, s)) for s in seq])
    case("the same presses: both table entries hold the rectangle of each state, and no other byte of the four lines changes",
         all(s[3] == all_rects((k + 1) % NS) and s[5] for k, s in enumerate(seq)))
    case("the 2.25:1 state: fit word 3, constants `moveq.w lr,#4` / `it eq; moveq r0,#9` (height = width x 4/9), rectangle (0, 80, 640, 320)",
         seq[1][2] == 2 and seq[1][3] == all_rects(2) and RECT_T[2] == (0, 80, 640, 320) and BWORDS[2] == (0x0E04F04F, 0x2009BF08))
    case("every buffer unmapped, every descriptor closed, every buffer freed, /dev/mem opened O_RDWR|O_SYNC",
         released(e) and e.n("alloc") == NS + 1 and all(c[2] == "0x101002" and c[1] == "/dev/mem" for c in e.calls if c[0] == "openat"))
    case("the layout request is case 0 (in and out all zero)", all(c[1] == bytes(48) and c[2] == bytes(16) for c in e.calls if c[0] == "layout"))
    case("dlsym is asked for the three libsencore names with RTLD_DEFAULT",
         {(c[1], c[2]) for c in e.calls if c[0] == "dlsym"} == {(0, "_Z9dmm_allocjPj"), (0, "_Z8dmm_freej"), (0, "sen_dma_transfer")})
    case("every transfer is one of the four 64-byte lines (the model refuses any other)", e.n("xfer") > 0)
    f = new()
    seq = []
    for ev_id in (C3, C2, C3, C2):
        okregs, ev = f.press(ev_id)
        seq.append(okregs and ev == NOOP)
    case("C3 (0x2150006) steps the same way as C2, and the two mix: C3, C2, C3, C2 from 3:2 end in 3:2 with its rectangles",
         all(seq) and f.picture() == 0 and f.entries() == all_rects(0) and f.n("layout") == 4 and rest_same(f))
    for ev_id in TRIGGERS:
        for label, mode in (("stills (2)", 2), ("playback (4)", 4), ("mode 0", 0), ("mode 1", 1)):
            f = new(mode=mode)
            okregs, ev = f.press(ev_id)
            case("%s in %s: event untouched, only the mode read, nothing else called, nothing read or written" % (hex(ev_id), label),
                 okregs and ev == ev_id and [c[0] for c in f.calls] == ["mode"] and f.picture() == 0 and f.entries() == all_rects(0))
    for ev_id in (0x2150000, 0x2150001, 0x2150002, 0x2150004, 0x2150005, 0x2150007, 0x2150103, 0x3150003, 0x216003E, 0x20F00BE, NOOP, 0):
        f = new()
        okregs, ev = f.press(ev_id)
        case("event %#x in movie mode: untouched, nothing called" % ev_id, okregs and ev == ev_id and not f.calls)
    for label, fail in (("dlsym finds no sen_dma_transfer", {"dlsym": "sen_dma_transfer"}), ("dlsym finds no dmm_alloc", {"dlsym": "_Z9dmm_allocjPj"}),
                        ("dmm_alloc fails", {"alloc": 1}),
                        ("the read of the fit word's line fails", {"xfer": (0, line_of(FIT))}), ("the write of the fit word's line fails", {"xfer": (1, line_of(FIT))}),
                        ("the read of the constants' line fails", {"xfer": (0, line_of(CONST))}), ("a write is lost (read-back differs)", {"lost": 1}),
                        ("a read moves nothing (the fill stays)", {"noread": 1})):
        f = new(fail=fail)
        okregs, ev = f.press()
        freed = f.n("free") == (0 if fail.get("alloc") or fail.get("dlsym") else 1)      # a buffer that was never given is not freed
        case(label + ": swallowed, picture unchanged, tables unchanged, no layout call, everything released",
             okregs and ev == NOOP and f.picture() == 0 and f.entries() == all_rects(0) and not f.n("layout") and not f.maps and not f.fds and freed)
    f = new(fail={"xfer": (1, line_of(CONST))})
    okregs, ev = f.press()
    case("the write of the constants' line fails (the fit word is already written): swallowed, no layout call, tables untouched, everything released",
         okregs and ev == NOOP and not f.n("layout") and f.entries() == all_rects(0) and released(f) and f.word(CONST) == BWORDS[0][0])
    for name, addr, guards, _, _ in LINES[:2]:
        for g in guards:
            cp = cp_model()
            a = addr + 4 * g
            cp[line_of(a)][a - line_of(a)] ^= 1
            f = new(cp)
            before = {k: bytes(v) for k, v in f.cp.items()}
            okregs, ev = f.press()
            case("guard %+d of line %s not as expected: nothing written anywhere, no layout call" % (g, name),
                 okregs and ev == NOOP and {k: bytes(v) for k, v in f.cp.items()} == before and not f.n("xfer", 1) and not f.n("layout"))
    f = new(cp_model(fit=3, rects=(STOCK,) * NT))               # the stock image: no fill word
    okregs, ev = f.press()
    case("without lcdfill (fit word 3 with the 9/16 constants = no known state): nothing written, no layout call", okregs and ev == NOOP and not f.n("xfer", 1) and not f.n("layout"))
    for k in range(NS):                                        # any start state: the state is read from the coprocessor
        f = new(cp_model(fit=FITS[k], bstate=k, rects=(k,) * NT))
        okregs, ev = f.press()
        case("starting in state %d: one press goes to state %d" % (k, (k + 1) % NS),
             okregs and f.picture() == (k + 1) % NS and f.entries() == all_rects((k + 1) % NS) and rest_same(f))
    for k, fit in ((1, 0), (2, 0), (3, 0), (0, 3)):             # fit word and constants disagree
        f = new(cp_model(fit=fit, bstate=k, rects=(k,) * NT))
        okregs, ev = f.press()
        case("constants of state %d with fit word %d (they disagree): nothing written, no layout call" % (k, fit), okregs and not f.n("xfer", 1) and not f.n("layout"))
    f = new(cp_model(rects=(STOCK,) * NT))                     # the fill word alone (tables stock)
    okregs, ev = f.press()
    case("with the fill word but stock tables: one press writes the 2:1 rectangle into both", okregs and f.picture() == 1 and f.entries() == all_rects(1) and rest_same(f))
    for idx, (name, addr, guards, _, _) in enumerate(LINES[2:]):
        for g in guards:
            cp = cp_model()
            a = addr + 4 * g
            cp[line_of(a)][a - line_of(a)] ^= 1
            f = new(cp)
            okregs, ev = f.press()
            ent = f.entries()
            case("guard %+d of table line %s not as expected: that entry untouched, the other written, picture changed, one layout call" % (g, name),
                 okregs and f.picture() == 1 and ent[idx] == RECTS[0] and all(v == RECTS[1] for j, v in enumerate(ent) if j != idx) and f.n("layout") == 1)
    for idx in range(NT):
        cp = cp_model()
        a = ENTRIES[idx] + 2
        cp[line_of(a)][a - line_of(a)] = 77                   # an entry that is none of the known rectangles
        f = new(cp)
        before = bytes(f.cp[line_of(a)])
        okregs, ev = f.press()
        others = [v for j, v in enumerate(f.entries()) if j != idx]
        case("table entry %s holds no known rectangle: it is left alone, the rest as designed" % LINES[2 + idx][0],
             okregs and f.picture() == 1 and others == [RECTS[1]] * (NT - 1) and bytes(f.cp[line_of(a)]) == before and f.n("layout") == 1)
    for label, fail, want in (("the read of a table line fails", {"xfer": (0, line_of(ENTRIES[0]))}, [RECTS[0], RECTS[1]]),
                              ("the write of a table line fails", {"xfer": (1, line_of(ENTRIES[1]))}, [RECTS[1], RECTS[0]])):
        f = new(fail=fail)
        okregs, ev = f.press()
        case(label + ": picture changed and layout requested all the same, that entry unchanged, everything released",
             okregs and f.picture() == 1 and f.entries() == want and f.n("layout") == 1 and released(f) and f.n("alloc") == 1)
    return out, fails


def main():
    img = locate_file.locate(BUILD, "appFw.so").read_bytes()
    img4 = locate_file.locate("a7iv_602", "appFw.so").read_bytes()
    facts = check_files(img, img4)
    words, rows = pool()
    (SRC.parent / "pool.h").write_text(pool_h(words, rows), encoding="utf8", newline="\n")
    code, stub, step, old, hook = build()
    assert img[HOOK1:HOOK1 + 4] == old
    res, fails = tests(img, code, hook)
    for r in res:
        print(("PASS  " if r["ok"] else "FAIL  ") + r["case"])
    if fails:
        raise SystemExit("%d emulated case(s) failed" % len(fails))
    patches = []
    for k in range(0, len(code), 16):
        chunk, was = code[k:k + 16], img[CAVE + k:CAVE + k + len(code[k:k + 16])]
        if chunk == was:
            continue
        patches.append({"binary": "appFw.so", "kind": "cave", "file_off": hex(CAVE + k), "va": hex(CAVE + k), "old": was.hex(), "new": chunk.hex(), "code": True,
                        "note": "cave bytes %#x-%#x (in .rela.dyn: the old bytes are relocation entries, applied at load and not read again)" % (CAVE + k, CAVE + k + len(chunk))})
    patches.append({"binary": "appFw.so", "kind": "hook", "file_off": hex(HOOK1), "va": hex(HOOK1), "old": old.hex(), "new": hook.hex(), "code": True,
                    "note": "process_input_event: `%s` -> `b %#x` (the stub does it)" % (HOOK1_OLD, CAVE)})
    design = {"design": "lcdcycle_zv_v1",
              "title": "ZV-E1 2.02: C2 steps the rear-screen preview 3:2 -> 2:1 -> 2.25:1 -> 2.4:1 in movie mode and keeps the focus frames: VDF words and "
                       "the frame widgets' expected rectangle, written from appFw",
              "generated_by": "build/build_lcdcycle_zv.py", "library": "appFw.so", "artifact_sha256": {"appFw.so": hashlib.sha256(img).hexdigest()},
              "coprocessor_image_sha256": hashlib.sha256(CP).hexdigest(), "build": BUILD,
              "ported_from": "lcdcycle_c2_v1 (A7C II 2.01; built and emulated, not run), itself lcdcycle_v6 (A7 IV 6.02; works on that camera, F858, F969); "
                             "the 2.25:1 state from lcdcycle_s3_v3 (A7S III 5.01)",
              "write_order": "the patches in the listed order to apply (cave, then the hook); the reverse order to put back",
              "trigger": hex(TRIGGERS[0]), "triggers": {"0x2150003": "EVENT_INPUT_KEY_TACT_CUSTOM2_ON (C2: the ZV-E1's rear key, 'Step zoom' by default)",
                                                        "0x2150006": "EVENT_INPUT_KEY_TACT_CUSTOM3_ON (C3; this body has no C3 key)"},
              "ignored_event": hex(NOOP), "calls": {k: hex(v) for k, v in SYMS.items()},
              "cave": {"from": hex(CAVE), "bytes": len(code), "region": ".rela.dyn", "region_end": hex(CAVE_END), "page_end": hex(CAVE_END),
                       "inside_zero_bytes": False, "old_bytes": "relocation entries of types %s (257 = R_AARCH64_ABS64), applied by the loader when appFw.so is mapped and not read again" % facts["relocation_types_in_cave"],
                       "why_not_after_the_segment": "the first segment ends at %s: the 16-aligned tail of its last page is %d bytes; the routine needs %d"
                                                    % (facts["first_segment_end"], facts["tail_cave_bytes"], len(code)),
                       "dynamic": facts["rela_dyn"], "relocation_types_in_cave": facts["relocation_types_in_cave"], "tail_note": facts["tail_note"]},
              "step_routine": "build/lcdcycle_zv/step.c at %#x (%d bytes)" % (STEP_AT, len(step)), "stub_bytes": len(stub),
              "lines": [{"name": n, "line": hex(l), "first_site_word": hex(l + 4 * b), "words": nw, "guards": ng, "candidates": nc} for n, l, b, ng, nc, nw, _, _ in rows],
              "states": {n: [hex(FITS[k])] + [hex(x) for x in BWORDS[k]] for k, n in enumerate(("3:2", "2:1", "2.25:1", "2.4:1"))},
              "frame_rectangles": {"entries": [hex(a) for a in ENTRIES], "3:2": list(RECT_T[0]), "2:1": list(RECT_T[1]), "2.25:1": list(RECT_T[2]),
                                   "2.4:1": list(RECT_T[3]), "stock": list(RECT_T[4]),
                                   "note": "{x, y, w, h} u16 in a 640x480 grid, row 1 (rear panel) column 3 (16:9 picture) of the two tables (AF window, tracking); the widgets "
                                           "accept 5 units either way. 3:2, 2:1 and 2.4:1 are the values that work on the A7 IV (F969); 2.25:1 is (0, 80, 640, 320) by the "
                                           "same rule (height 480 x 1.5 / 2.25), not run on any camera"},
              "checked_in_files": {"system_mode_field": facts["system_mode_field"], "dlsym_got": facts["dlsym_got"], "frame_widget_table_loads": facts["frame_widget_table_loads"]},
              "goes_with": ["a ZV-E1 open-gate state (not part of this design)",
                            "a ZV-E1 lcdfill: fit word 0x1f5c88 3 -> 0 and the two entries 0xe9b420, 0xe9b498 (0, 38, 640, 404) -> (0, 0, 640, 480): without the fill "
                            "word a press does nothing"],
              "not_checked": ["on a camera: nothing of this design has run on a ZV-E1",
                              "that the key labelled C2 sends 0x2150003 (the name record is the same as on the A7 IV, where CUSTOM3 = C3 was seen on the camera; the "
                              "ZV-E1 has CUSTOM, CUSTOM2, CUSTOM3, CUSTOM5 and CUSTOM6 events and two physical custom keys, C1 and C2)",
                              "that system mode 3 is movie on this camera (the accessor is found by call position; its field offset differs from the A7 IV's)",
                              "that dlsym(RTLD_DEFAULT) finds libsencore's three functions in im.elf (the names are exported by this build's libsencore.so)",
                              "that the rear panel reports panel code 1 (3:2) and that the frame widgets use row 1 for it ([dev+0x244] non-zero, as on the A7 IV)",
                              "that the AF-window and tracking widgets are the only ones that compare the live-view rectangle (the A7C II's third, remote-send "
                              "widget is not in this build)",
                              "the 2.25:1 rectangle (0, 80, 640, 320): derived, not seen on a camera",
                              "that the picture-ratio flag (bit 0 of its fourth argument; 1 selects 100/235) is 0 in the open-gate state, as on the A7S III",
                              "that nothing reads .rela.dyn after load on this camera (true of the glibc and musl loaders)"],
              "note": "put back (level 20) removes the code; the coprocessor words stay in the mode last chosen until a cold boot. In movie mode the C2 key's "
                      "assigned function (Step zoom by default) no longer runs (the press is turned into the ignored event); in stills C2 is normal",
              "patches": patches}
    (ROOT / "modding/designs/lcdcycle_zv_v1.json").write_text(json.dumps(design, indent=1) + "\n", encoding="utf8", newline="\n")
    (ROOT / "evidence/zve1").mkdir(parents=True, exist_ok=True)
    (ROOT / "evidence/zve1/lcdcycle_zv_v1_emu.json").write_text(json.dumps({"generated_by": "build/build_lcdcycle_zv.py", "cases": res, "cave_bytes": len(code),
                                                                            "appFw_sha256": hashlib.sha256(img).hexdigest(), "cpapp_sha256": hashlib.sha256(CP).hexdigest()},
                                                                           indent=1) + "\n", encoding="utf8", newline="\n")
    print("cave %d bytes from %#x (stub %d, lcd_step %d at %#x); ends at %#x of %#x; %d patch entries; %d cases pass"
          % (len(code), CAVE, len(stub), len(step), STEP_AT, CAVE + len(code), CAVE_END, len(patches), len(res)))


if __name__ == "__main__":
    main()
