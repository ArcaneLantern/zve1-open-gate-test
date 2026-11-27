# ZV-E1 (`2.02`) Physical Hardware Report, Gyroflow `rtmd` Findings & 3:2 NRT XML (`NrtMetaWrapper::Init`)

This directory contains a standalone, clean-room hardware field report and cross-body `libmpr.so` offset/guard verification script for the Sony **ZV-E1 (`2.02`)**, **a7S III (`5.01`)**, and **FX3 (`7.02`)** 3:2 (`3840×2560`) open-gate pipeline.

No existing kit files or pinned `.so` binaries are modified here.

---

## 1. ZV-E1 (`2.02`) Physical Hardware Test Summary (macOS `26.3.1` `arm64`)

Tested on a physical **Sony ZV-E1** (`fw 2.02`, build `32000_08.2025101101`) from a 10s battery-pull cold boot:

1. **Read-only preflight (`check`)**: Connected in Stills mode -> `VERDICT READY` (`stock`, `DeviceInfo.xml` verified).
2. **6-step volatile RAM apply**: `dmmwb` -> `ogsq (0x8c0 + 0x820)` -> `outsz2560` -> `ogfile2560 + M19` -> `lcdfill` -> `lcdcycle` -> all 6 steps `OUTCOME: DONE`, helper removed from `/tmp/jiritsu/`.
3. **Movie mode closing `dump` & live view**: Switched to Movie (`23.98p` `XAVC HS 4K` and `XAVC S 4K`), captured closing `dump`, saw **clean 3:2 full-height rear LCD live view** (including AF/tracking frames and `C2` aspect cycle; no purple/black live-view corruption seen on ZV-E1).
4. **Hardware clips recorded (`C6433.MP4`–`C6436.MP4` + stock `C6437.MP4`)**:
   - **Open-gate resolution:** `3840×2560`, `23.976p`, `HEVC Main 10 L5.0`, `63–68 Mbps`.
   - **Stabilization:** **SteadyShot Active** and **Dynamic Active** both worked smoothly during recording (`0` dropouts, `0` constant-cadence drift across `384`–`756` frames).
   - **Sony `rtmd` telemetry:** Intact **`2000 Hz`** gyro (`0xe43b`), accel (`0xe44b`), and lens breathing (`LPIF`), `0.0 ms` timestamp drift across all clips.
5. **Clean putback & verification:** Switched `C2` back to `3:2`, ran 6-step `putback` -> `OUTCOME: DONE`, then confirmed `check` returned `VERDICT READY (stock)` (plus verified warm power-switch partial reset restores coprocessor while `av-cam`/`libmpr` stay applied until putback or `>= 10s` battery pull).

---

## 2. Measured IMX510 Hardware Readout (`rtmd` Tag `0xe40e`)

Sony's embedded `rtmd` timed-metadata track directly records each frame's sensor readout duration in KLV tag **`0xe40e`** (parsed by Gyroflow's `telemetry-parser`):

| Mode (Sony ZV-E1 `2.02`, IMX510) | Active Geometry | FPS / Codec | Sony `rtmd` `0xe40e` | Notes |
|---|---|---|---:|---|
| **Stock 16:9** (`C6437.MP4`) | `3840×2160` | `23.976p` XAVC HS 4K | **`9.555 ms`** | Unpatched stock baseline |
| **Open Gate 3:2** (`C6433`–`C6436.MP4`) | `3840×2560` (`0x8c0`) | `23.976p` XAVC HS 4K | **`12.336 ms`** | Consistent across all 4 open-gate clips (`1.291×` stock) |

Because ZV-E1, a7S III, and FX3 share the same `IMX510` `4288×2848` `MULTI_REC` open-gate sensor readout timing in `0x8c0` (`23.976p`), `12.336 ms` reflects the actual hardware rolling-shutter readout time for `3840×2560`.

---

## 3. Critical Gyroflow Pitfall Found: `ConvertVPCToLevel` vs. `NrtMetaWrapper::Init`

While testing the recorded `3840×2560` ZV-E1 clips in **Gyroflow `v1.7.1`**:

- **Symptom:** Even though `tkhd`/`stsd`/`VPRF` were `3840×2560` and all `2000 Hz` `rtmd` KLV packets were intact, Gyroflow `v1.7.1` initially reported `Contains gyro: No` and blank camera/lens fields.
- **Root cause (in `libmpr.so` Ghidra trace & clip atom inspection):**
  - Gyroflow's `telemetry-parser` requires `<Device manufacturer="Sony".../>` inside the trailing `meta -> xml ` box (`NonRealTimeMeta`).
  - Patching `ConvertVPCToLevel` (`2160 -> 2560`) breaks `FUN_00235628` (`0x99`) inside `NrtMetaWrapper::Init`, causing `NrtMetaWrapper::Init` to abort before `<Device>`, `<VideoLayout>`, or `<VideoFrame>` are written — leaving a truncated `<NonRealTimeMeta .../>` atom (plus `16:9` sidecar `M01.XML`).
  - Reconstructing the missing trailing XML nodes (`<Device>`, `<VideoFrame>`, `<VideoLayout numOfVerticalLine="2560">`) non-destructively (keeping every video, audio, and `rtmd` frame byte-identical) immediately unlocked full Gyroflow `v1.7.1` detection:
    - `Detected camera: Sony ZV-E1`
    - `Detected lens: FE 24mm F1.4 GM 24.00 mm`
    - `Dimensions: 3840x2560`
    - `Contains gyro: Yes`
- **Clean In-Camera Fix (`NrtMetaWrapper::Init`):**
  - Leave `ConvertVPCToLevel` untouched so `FUN_00235628` succeeds normally.
  - Instead, patch two instructions directly inside `NrtMetaWrapper::Init`:
    1. **`L3-nrt-vline`**: Override `ldrh w0, [x20, #0x5e]` (`80be4079`) with `mov w0, #0xa00` (`00408152`) after `SetVideoFrame` succeeds (`<VideoLayout numOfVerticalLine="2560">`).
    2. **`L3-nrt-noasp`**: Override `mov w0, #1` (`20008052`) with `mov w0, #0` (`00008052`) to clear `b_aspectValid` passed to `SetVideoLayout` because Sony's NRT XML aspect enum table has no `3:2` entry (omits `<VideoLayout aspectRatio="16:9">` cleanly).

---

## 4. Six Additional `libmpr.so` Sites Beyond `L4-mp4size` (Cross-Body Verified)

PR `#2` promoted the two `L4-mp4size` (`RecAttribute.height`) sites. Below are the **6 companion sites** across `libmpr.so` (`ZV-E1 2.02`, `a7S III 5.01`, and `FX3 7.02`) covering **codec level calculation**, **trailing NRT XML**, and **in-camera playback validation**:

| Site Kind | Purpose | ZV-E1 (`2.02`) | a7S III (`5.01`) | FX3 (`7.02`) | Old -> New (Hex & ASM) |
|---|---|---|---|---|---|
| `L2-mp4-avc` | Existing `L4-mp4size` AVC 3840w height | `0x207d8c` | `0x223cc4` | `0x21ff3c` | `060e8152` -> `06408152` (`mov w6, #0x870` -> `#0xa00`) |
| `L2-mp4-hevc` | Existing `L4-mp4size` HEVC 3840w height | `0x207dd8` | `0x223d10` | `0x220074` | `060e8152` -> `06408152` (`mov w6, #0x870` -> `#0xa00`) |
| `L2-lvl-avc` | Preserve AVC L5.1/5.2 above `2160` | `0x20794c` | `0x223884` | `0x21fb0c` | `20040054` -> `22040054` (`b.eq` -> `b.hs`) |
| `L2-lvl-hevc` | Preserve HEVC L5.0/5.1/5.2 above `2160` | `0x207aa8` | `0x2239e0` | `0x21fc68` | ZV/S3: `c0030054`->`c2030054`; FX3: `80030054`->`82030054` |
| `L3-nrt-vline` | `NrtMetaWrapper::Init` XML vertical lines | `0x238108` | `0x254110` | `0x25027c` | `80be4079` -> `00408152` (`ldrh w0,[x20,#0x5e]` -> `mov w0,#0xa00`) |
| `L3-nrt-noasp` | `NrtMetaWrapper::Init` clear `b_aspectValid` | `0x238114` | `0x25411c` | `0x250288` | `20008052` -> `00008052` (`mov w0,#1` -> `mov w0,#0`) |
| `L4-play-w` | Playback validator `3840x2560` width | `0x20a194` | `0x2260cc` | `0x222330` | `01c08352` -> `01e08152` (`mov w1,#0x1e00` -> `#0xf00`) |
| `L4-play-h` | Playback validator `3840x2560` height | `0x20a198` | `0x2260d0` | `0x222334` | `011ca272` -> `0140a172` (`movk w1,#0x10e0` -> `#0xa00,lsl#16`) |

Run the included offline verification script against any unpacked `libmpr.so` to check its SHA-256, ELF magic, stock bytes, and surrounding 16-byte guard windows:

```bash
python3 -B contrib/zve1_nrt_xml_gyroflow/verify_libmpr_3x2_sites.py --selftest
python3 -B contrib/zve1_nrt_xml_gyroflow/verify_libmpr_3x2_sites.py --body zve1_202 --libmpr /path/to/zve1_202/libmpr.so
```

---

## 5. Additional Reference

Full redacted conformance artifacts, `bionz_clip_check.py`, `repair-nrt-xml`, and prebuilt macOS `OpenGate Studio.app` bundles are maintained at:
- [jeromykovatana/opengate-studio](https://github.com/jeromykovatana/opengate-studio) (`v0.1.4-alpha`, [`docs/conformance/zve1_202/CONFORMANCE_REPORT.md`](https://github.com/jeromykovatana/opengate-studio/blob/main/docs/conformance/zve1_202/CONFORMANCE_REPORT.md))
