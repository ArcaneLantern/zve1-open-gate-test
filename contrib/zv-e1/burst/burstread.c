/* ZV-E1 2.02 burst-timing reader. READ-ONLY. Reuses zvread.c (unmodified) for syscalls, output, SHA-256 and the one
 * coprocessor transfer call, cp_page(), whose direction is the constant 0 (coprocessor -> main memory).
 * It first requires the coprocessor code pages that were analysed to be byte-identical to cpapp-b.bin 2.02;
 * otherwise no data address is read. */
#define constructor unused                 /* drop zvread.c's own entry point; run() stays referenced and is never called */
#include "zvread.c"
#undef constructor
#include "burst_pages.h"                   /* generated: code_pages[] */

struct range { const char *name; u32 addr; u32 len; };
static const struct range ranges[] = {
    { "debug_byte",   0x19967a0, 16 },     /* +7 = 0x19967A7: interval override */
    { "interval_tab", 0x1a08900, 256 },    /* 0x1A08998..CF: per-category intervals */
    { "seq_state",    0x15b5e70, 128 },    /* LiroSeq state +0x100..0x17F: drive_mode +0x138, burst_count_max +0x120, customFps +0x12C */
    { "timer",        0x197ded0, 64 },     /* 0x197DEEC: +0x10 period, +0x0C target, +0x08 count, +0x14 precise */
};

static void burst_cp(void)
{
    u32 handle = 0;
    cp_phys = cam_dmm_alloc(CP_PAGE, &handle);
    if (!cp_phys) { puts_("!! buffer allocation failed\n"); return; }
    if ((cp_phys & 0x3f) || cp_phys < RAM_LO || cp_phys + CP_PAGE > RAM_HI) { puts_("!! buffer address not usable\n"); cam_dmm_free(handle); return; }
    i64 fd = sys_open("/dev/mem", F_RDONLY_SYNC, 0);
    if (fd < 0) { puts_("!! /dev/mem open failed\n"); cam_dmm_free(handle); return; }
    u64 lead = cp_phys & 0xfff, maplen = (lead + CP_PAGE + 0xfff) & ~0xfffUL;
    i64 m = sys_mmap_ro((int)fd, maplen, cp_phys - lead);
    if (m == -1) { puts_("!! mmap of the buffer failed\n"); sys_close((int)fd); cam_dmm_free(handle); return; }
    cp_buf = (const u8 *)m + lead;
    cp_ok = 1;

    int same_code = 1;
    for (u64 i = 0; i < sizeof code_pages / sizeof code_pages[0] && same_code; i++) {
        struct sha s; u8 dg[32];
        puts_("code "); putaddr(code_pages[i].address);
        if (!cp_page(code_pages[i].address)) { same_code = 0; break; }
        sha_init(&s); sha_add(&s, cp_buf, CP_PAGE); sha_end(&s, dg);
        same_code = same(dg, code_pages[i].sha256, 32);
        puts_(same_code ? " SAME\n" : " DIFFERS\n");
    }
    if (!same_code) puts_("!! the code is not the analysed 2.02 code; no data was read\n");
    else {
        int all = 1;
        for (u64 i = 0; i < sizeof ranges / sizeof ranges[0]; i++) {
            static u8 data[256];
            if (!cp_bytes(ranges[i].addr, data, ranges[i].len)) { all = 0; break; }
            puts_("data "); puts_(ranges[i].name); puts_(" "); putaddr(ranges[i].addr); puts_(" "); puthex(data, ranges[i].len); puts_("\n");
        }
        if (all) puts_("VERDICT READ OK\n");
    }
    sys_munmap((void *)m, maplen);
    sys_close((int)fd);
    cam_dmm_free(handle);
}

__attribute__((constructor)) static void burst_ctor(void)
{
    i64 fd = sys_open(RESULT_PATH, F_NEW, 0600);
    if (fd < 0) return;
    out_fd = (int)fd;
    puts_("zvburst 1 for ZV-E1 2.02; read-only\n");
    burst_cp();
    puts_("== done\n");
    sys_close((int)fd);
    out_fd = -1;
}
