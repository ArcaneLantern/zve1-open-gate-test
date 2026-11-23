# Port notes: A7S III 5.01 kit → ZV-E1 2.02

Everything here was read from the ZV-E1 2.02 firmware update. The firmware decrypts with the public key the A7 IV, A7C II and A1 II use: 1,446 files, and all 93 checksums are valid. **Nothing has run on a ZV-E1.** Each step of the kit was emulated: Unicorn ran the ZV-E1's own code where it mattered, and the built helper libraries against a model camera.

## What the ZV-E1 shares with the A7S III, and with the A7C II

- **Sensor: the A7S III's.** IMX510, the same drive modes in the same order, minus 0x8010 (39 modes instead of 40).
  - 0x8c0 (FF 4K 23.98p) is still mode 12. 0xe011, the full-height mode the patch borrows, moves from 37 to 36.
  - The same register-matrix column numbers: 0x8c0 uses column 11 and 0xe011 column 1.
  - The window, aux-stream, LC, crop and 0xdcd8a4 rows of both modes are byte-identical to the A7S III's.
- **Platform: the A7C II's.**
  - `kemco.txt` and `usbg_sen.ko` are byte-identical to the A7C II's: av-cam.bin at physical 0x401000000.
  - The stored drive-parameter record is 0x170 bytes.
  - The drive-parameter pointer is at control +0x684.
  - The parameter object is at +0x4ec, with the configuration at +0x54c.
- **USB service route.** `libsencore.so` holds the A7 IV/A7S III login keys (at 0x59a50, 0x59c50, 0x59e50) and the same file commands. `DeviceInfo.xml` is byte-identical to the A7 IV's, the A7S III's and the A7C II's. So the known-answer read cannot tell the bodies apart; the helper itself checks which camera it is on (identity hashes of three libraries and four code pages).

## Sensor side: `ogsq_zv_v1` (the A7S III's `ogsq_s3_v5`)

| Item | A7S III 5.01 | ZV-E1 2.02 |
|---|---|---|
| mode ids | 0xc70624 (40) | 0xdcc524 (39) |
| column map | 0xc703cc | 0xdcdd00 (second value 3 instead of 4 for every mode) |
| register matrix | 0xf2eb78, 489 rows | 0x10cdaf0, 499 rows |
| receiver type tables | 0xc70e44, 0xc717a4 | 0xdccd10, 0xdcd634 |
| timing, 59.94 / 50 system | 0xc71024 / +0x3c0 | 0xdccee4 / +0x3a8 |
| windows: stream 0 / stream 1 / LC | 0xd67c00 / 0xd681f0 / 0xd687e0 | 0xeb6292 / 0xeb685c / 0xeb6e26 |
| read-out table | 0xd68a10, 18-byte rows | 0xeb7048, **16-byte rows** |
| crop / class | 0xc706c4 / 0xc709e4 | 0xdcc5c0 / 0xdcc8cc |
| geometry row of 0x8c0 | 0xc1801c | 0xd7c034 |
| stored records in RAM | 0x1fe0504, 0x15c each | 0x25d9fa4, 0x170 each |
| sensor object | 0x12a41f0 | 0x17f1f64 |
| record selector | 0x256128 | 0x26f894 |
| 0x8c0/0x820 picture pair | 0xbcfff8 / 0xbd0bb0 | 0xd35f14 / 0xd36acc |

Found through the code that builds each address: `build/port_addr.py` (new) and the map's matching tools. The selector was emulated: 0x8c0 and 0x820 share one pair, as on the A7S III.

**Differences in the stock values the design changes:**

- **Receiver type.** The 4K rows hold 6, 3 (A7S III 5, 3); every 10-bit mode on the ZV-E1 holds 6. The design writes 0, 2 (0xe011's), as on the A7S III.
- **24p timing row.** 287 × 5220, P 87, E 56 (A7S III 266 × 5628, P 67, E 53). The frame length is the same: 1,501,500 units = 23.976 fps. The design writes the A7S III's working row, 313 × 4788, P 57, E 34 (E < P). The 50 Hz row is identical on both bodies.
- **Read-out table.** No frame-length fields (they are 0 in every row). Only the row fields 618 → 728 change.
- **Geometry row.** It has one more field, +8, which holds 418 for 0x8c0 and 0 on the A7S III. It is left alone. **Not known what it is.**

**Picture records.** The ZV-E1's stock 4K pair differs from the A7S III's in about 50 words: 80 leading columns instead of 20, line-length words like the A7C II's, and a single-row flag that is set. So the records were rebuilt, not copied. The model is `build_og_s3.py`'s: the A7 IV's field classes, frame fields from this body's full-height still pair (0xd4264c / 0xd43204), and this body's own packers (CamArc 0x267f48, CamNrs 0x7885cc, CamSig 0x7904e0, CamLrc 0x788588, Dev 0x787ae8 / 0x78796e, fit 0x790040).

- All 154 model fields fit the ZV-E1's stock records.
- The ZV-E1's packers reproduce every stock packer word.
- The result has the same scaler numbers as the A7S III's working v5: Lrc 2180 × 2848 → 2176 × 2408, final 2144 + 2096 × 2392.
- Then the v5 link-format words for a 12-bit link. The rule holds on all 38 ZV-E1 records.

**Stored record.** The ZV-E1's own calculator (0x390fa0) was run with every cell applied: 68 bytes differ, and +6/+7 carry the sampling ratio 16/19. Two bytes are left alone: the A7S III camera's run-time bytes, moved by 4 past +0x1c. **That is a guess.** If the camera holds other values there, step 1 refuses and writes nothing.

## Output size: `outsz2560_zv_v1`

The size table is filled by 0x4aadd8 into base 0x19964c4 + 0x50, as the A7C II's, including its extra 8K class. The 3840 × 2160 entry at 0x199655c becomes 3840 × 2560. There are two guards.

## Encoder side: `ogfile2560_hs_s_zv_v1`

- libmpr.so `g_videoParamComb` is at the A7 IV's position −0x205c0. av-cam.bin: unit types 0x38f848, descriptors 0x38f8e8, clip table 0x38d7ec (codes 3 / 23, as on the A7S III).
- **The descriptor table has 647 rows of 0x88 bytes** (A7S III: 689 × 0x90).
- The same 29 descriptors are chosen: 101 av-cam + 4 libmpr sites.

## Screen: `lcdfill_zv_v2` and `lcdcycle_zv_v1`

The rear screen is 3.0-type, 1,036,800 dots = 720 × 480 = **3:2**, and there is **no viewfinder**. So the A7S III's 4:3 step (`lcdratio32_s3_v1`) does not apply. The A7 IV / A7C II step does instead:

- **`lcdfill_zv_v2`:**
  - Fit word 0x1f5c88 goes from 3 to 0. The fit function at 0x1f5c34 and its tables are byte-identical to the A7 IV's.
  - The rear-panel 16:9 entry of the AF-window and tracking-frame tables (0xe9b420, 0xe9b498) goes from (0, 38, 640, 404) to (0, 0, 640, 480).
  - That is 5 words. The A7C II's remote-send frame widget does not exist on this body.
- **`lcdcycle_zv_v1`:** a routine in appFw.so's .rela.dyn page (cave 0x17d6000, 1,460 bytes) and one branch at 0x1f7c61c.
  - **C2** steps 3:2 → 2:1 → 2.25:1 → 2.4:1 → 3:2 in movie mode (event 0x2150003). The ZV-E1 has C1 (Background Defocus) and C2 (Step zoom); C2 was chosen.
  - 66 emulated cases pass.
  - That the physical C2 key sends 0x2150003 is assumed from the event name.

## The kit

- **Helper libraries:** `helper_zv/` holds `zvread.c` (from `s3read.c`, text changes only) and the A7 IV helper's write levels with this body's tables: `gen_zv_write.py` (from the A7C II's) and `build_zv_write.sh`.
- **Scripts:** `zv_run.py` and `zv_apply.py` (from `s3_run.py` / `s3_apply.py`). The dump decoder's RAM addresses were ported too. Two are predictions, not matches: the second scaler's block and input words.

**Checked offline:**

- Read-only libraries: 10 cases.
  - Stock reads READY.
  - Applied reads TARGET everywhere.
  - An A7S III image is refused.
  - Without the av-cam reservation, av-cam.bin is not read.
  - With an existing result, the helper does nothing.
- Write libraries: 33 cases. Apply, apply again, put back byte for byte, foreign bytes, a wrong guard, lost writes undone, the C2 hook written last and removed first.
- Every launcher: `--selftest` and `--dry-run`.
- The Android app's Python side, on the kit's simulated camera:
  - check;
  - the five-step apply and closing session;
  - put back;
  - a cancelled dialog;
  - Stop waiting.

## Not known until a ZV-E1 runs it

- Everything the A7S III kit left open: the live-view fault when movie mode is entered from stills, exposure and autofocus, and 60p.
- Whether receiver type 6 (the ZV-E1's 4K) behaves like the A7S III's 5 when replaced.
- The geometry row's extra field, and the stored record's run-time bytes.
- Whether the power switch removes the patch on this body.
- The rear panel's type byte (expected 3).
- The physical C2 key's event.
- The live-view and preview behaviour of the AI-unit body.
