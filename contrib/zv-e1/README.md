# ZV-E1 (fw 2.02): PAL 25p open gate, HEVC 10-bit at 25p, RAW burst timing

Contributed research on top of this kit. **One camera, one tester.** RAM only: a 10 s battery pull restores stock.
The power switch alone leaves a mixed state, as the main README says. This folder does not change any file of the kit
and ships no binaries: rebuild from source and review before running. The paths to your firmware extraction
(`zve1fw/...`) must be adjusted. After removing local paths the scripts were syntax-checked, **not re-run**.
Some comments and the filenames of private dumps come from the contributor's own setup.

## What was seen

| Item | Result |
|---|---|
| PAL 25p open gate, mode `0x820` (`pal25/`) | 3840×2560. Steps L13, P5 (replaces L5), L16, M19, S16, C19: 6/6 DONE |
| HEVC 10-bit 4:2:0 at 25p (`hevc25/`) | `C5108.MP4`: HEVC Main 10, `hvc1`, yuv420p10le, 3840×2560, 25/25 fps, level 150, 95.5 Mbps, 1656 frames, full decode without errors |
| RAW burst interval table (`burst/`) | stock 100 ms; 80 ms gave **12.49 fps** over 42 lossless-compressed 14-bit ARW (FE 70-200mm F4 G, 1/250) |

Not checked: framing against a chart, long clips, audio, HEVC in 16:9 only, the H20 put back on camera. The clip's Sony XML
still says `HEVC_3840_2160_M10P@L5HT`, 16:9.

Requirements: SteadyShot **Off or Standard** (Active uses mode `0x2820`, not patched by the PAL step); APS-C, Proxy and
S&Q off; no 50p/100p while applied. For PAL XAVC HS 4K, `appFw.so` only has 24p, 60p/50p and 120p/100p option strings,
so there is no 25p entry in that menu.

## How HEVC 25p works

The menu entry `XAVC S 4K 25p 100M 4:2:0 8bit` is redirected in `libmpr.so` so the encoder gets HEVC 4:2:0 10-bit.

| Site in `libmpr.so` | Change |
|---|---|
| cave `0x67000` (108 B, inside `.rela.dyn`, applied once at load) | the new code |
| `0xe1bc0` `SetMovieRecParam` | VPC 0 (AVC 4:2:0 8) with quality 12 (100M) and frame rate 2 (25p) becomes VPC 5 |
| `0xf18bc` HEVC rate check | class 2 (no table row) becomes 3 |
| `0x207aa4` `hvcC` level | height 2560 treated like 2160 |

Emulation (before the camera run): 252 parameter combinations, fps 0..23, `hvcC` level 0x96, apply / re-apply / put back
bit-exact (stock and with M19), refusal on unexpected bytes, rollback on a failure at each of the 10 writes.

## Step by step

1. Check the menu shows Ver. 2.02. USB mode: Mass Storage. Run the kit's `check_readonly`.
2. Build with `pal25/build_og_pal25_zv.py` (it also needs your own read-only PAL dump, not published) and
   `hevc25/build_h19.py`. Run both `verify_*_emu.py`. Review the output.
3. Battery out 10 s. Boot on **stills**. Camera set to PAL.
4. Apply in this order (the kit's runner needs pins added for the new libraries): L13, P5, L16, M19, H19, S16, C19.
   Every step must say DONE.
5. Movie mode, choose `XAVC S 4K 25p 100M 4:2:0 8bit`, record. Check the file with `ffprobe`.
6. Back to stock: battery out 10 s.

## RAW burst (experimental)

Interval table in coprocessor RAM at `0x1A08998`, 16 bytes per category, values in ms. Stock read: categories 0 and 1:
100, 125, 166; category 2: 100, 200, 250. Only the first level was changed (taken to be Hi+, inferred).

| Setting | Result |
|---|---|
| 80 ms (`build_burst80.py`, B16/B17) | 42 shots, 12.49 fps, intervals 78 to 82 ms. A second burst: 12.08 fps (starts at ~100 ms) |
| 55 ms, PAL (`build_burst55.py`, F16/F17, after 80) | mean 13.19 fps over 56 shots; intervals on a 20 ms grid (60 / 80 / 100) |
| 50 ms, NTSC (`build_burst50.py`, G16/G17, after 55) | intervals on a 16.68 ms grid, shortest 65 ms |

18 fps was **not** reached. Long bursts, heat, AF and image quality were not tested; RAW data was not decoded (file
structure and thumbnails only). The builders read a `burst-read` dump of your own camera (not published).

## Dead ends (so nobody repeats them)

- 12-bit stills by copying sensor mode `0xE011` cells over `0xA000`: **broken photos** (black with a pink strip). Not included.
- Forcing the `CamNrOnOff` branch (byte at `0x382044`): no measurable noise difference in video at ISO 102400.
- Open gate at full 4240 width at 50p: no 50/60 fps mode in the tables reads that wide.

## Credits

All of this builds on **ArcaneLantern**'s ZV-E1 / A7S III open-gate kit (GPL-3.0): its helper `readcheck.c`, designs
(M19, `ogsq_zv_v2`) and methods. Thanks also to its contributors (itsAllexB, jeromykovatana). USB service access builds on
[Sony-PMCA-RE](https://github.com/ma1co/Sony-PMCA-RE) by ma1co. Done with AI assistance (Claude, Gemini); tested on
camera by the contributor. GPL-3.0, like the kit. Use at your own risk.
