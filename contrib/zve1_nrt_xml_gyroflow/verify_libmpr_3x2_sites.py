#!/usr/bin/env python3
"""Read-only offline verifier for Sony BIONZ XR 3:2 libmpr.so patch sites and guards.

Covers ZV-E1 (2.02), a7S III (5.01), and FX3 (7.02):
  - L2-mp4-avc / L2-mp4-hevc  (existing PR #2 RecAttribute height 2160 -> 2560)
  - L2-lvl-avc / L2-lvl-hevc  (codec level calculation b.eq -> b.hs above 2160)
  - L3-nrt-vline / L3-nrt-noasp (NrtMetaWrapper::Init 2560 XML without aborting Gyroflow <Device>)
  - L4-play-w / L4-play-h     (playback validator 3840x2560 alongside 3840x2160)
"""
from __future__ import annotations

import argparse
import hashlib
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PatchSite:
    kind: str
    offset: int
    old_hex: str
    new_hex: str


@dataclass(frozen=True)
class GuardWindow:
    offset: int
    bytes_hex: str
    note: str


@dataclass(frozen=True)
class BodySpec:
    body_id: str
    camera: str
    firmware: str
    libmpr_sha256: str
    sites: tuple[PatchSite, ...]
    guards: tuple[GuardWindow, ...]


BODY_SPECS: dict[str, BodySpec] = {
    "zve1_202": BodySpec(
        body_id="zve1_202",
        camera="Sony ZV-E1",
        firmware="2.02",
        libmpr_sha256="e45dde41291cf45dd80897e0d9fa03818c1cdc14ae4d466c64f3d48af419e7cd",
        sites=(
            PatchSite("L2-mp4-avc", 0x207D8C, "060e8152", "06408152"),
            PatchSite("L2-mp4-hevc", 0x207DD8, "060e8152", "06408152"),
            PatchSite("L2-lvl-avc", 0x20794C, "20040054", "22040054"),
            PatchSite("L2-lvl-hevc", 0x207AA8, "c0030054", "c2030054"),
            PatchSite("L3-nrt-vline", 0x238108, "80be4079", "00408152"),
            PatchSite("L3-nrt-noasp", 0x238114, "20008052", "00008052"),
            PatchSite("L4-play-w", 0x20A194, "01c08352", "01e08152"),
            PatchSite("L4-play-h", 0x20A198, "011ca272", "0140a172"),
        ),
        guards=(
            GuardWindow(0x0, "7f454c46020101030000000000000000", "ELF64 magic"),
            GuardWindow(0x207930, "2007005420058052c0035fd620504079", "pre L2-lvl-avc"),
            GuardWindow(0x207950, "00058052c0035fd6c2149e52202040b9", "post L2-lvl-avc"),
            GuardWindow(0x207A90, "1f044071e0179f1a00cc0011c0035fd6", "pre L2-lvl-hevc"),
            GuardWindow(0x207AB0, "1f00026b400200541fe0107161060054", "post L2-lvl-hevc"),
            GuardWindow(0x207D70, "28668c52c82eac721c00001422008052", "pre L2-mp4-avc"),
            GuardWindow(0x207D90, "07e08152f7ffff172200805203008052", "post L2-mp4-avc"),
            GuardWindow(0x207DC0, "07c08352070000142200805203008052", "pre L2-mp4-hevc"),
            GuardWindow(0x207DE0, "28668c52c80ead72024400b9221040b9", "post L2-mp4-hevc"),
            GuardWindow(0x20A180, "010ea1721f00016b6100005480008052", "pre L4-play"),
            GuardWindow(0x20A1A0, "a0feff54c0035fd65f0000b9c0035fd6", "post L4-play"),
            GuardWindow(0x2380F8, "80ba407901008012bf630239a07300b9", "pre L3-nrt"),
            GuardWindow(0x238120, "804a40b9bfaf00b9a07f00b9c00640f9", "post L3-nrt"),
        ),
    ),
    "a7s3_501": BodySpec(
        body_id="a7s3_501",
        camera="Sony ILCE-7SM3 (a7S III)",
        firmware="5.01",
        libmpr_sha256="59ea134f5a40166379258126b7ff02c0b36b9846129b22b4cdc7faa52c927459",
        sites=(
            PatchSite("L2-mp4-avc", 0x223CC4, "060e8152", "06408152"),
            PatchSite("L2-mp4-hevc", 0x223D10, "060e8152", "06408152"),
            PatchSite("L2-lvl-avc", 0x223884, "20040054", "22040054"),
            PatchSite("L2-lvl-hevc", 0x2239E0, "c0030054", "c2030054"),
            PatchSite("L3-nrt-vline", 0x254110, "80be4079", "00408152"),
            PatchSite("L3-nrt-noasp", 0x25411C, "20008052", "00008052"),
            PatchSite("L4-play-w", 0x2260CC, "01c08352", "01e08152"),
            PatchSite("L4-play-h", 0x2260D0, "011ca272", "0140a172"),
        ),
        guards=(
            GuardWindow(0x0, "7f454c46020101030000000000000000", "ELF64 magic"),
            GuardWindow(0x223870, "c0035fd6205040791fe01071a0000054", "pre L2-lvl-avc"),
            GuardWindow(0x223890, "c2149e52202040b96207a0721f00026b", "post L2-lvl-avc"),
            GuardWindow(0x2239D0, "00cc0011c0035fd6205040791fc02171", "pre L2-lvl-hevc"),
            GuardWindow(0x2239F0, "1fe0107161060054202040b91f004671", "post L2-lvl-hevc"),
            GuardWindow(0x223CB0, "1c000014220080520300805244018052", "pre L2-mp4-avc"),
            GuardWindow(0x223CD0, "22008052030080524401805245008052", "post L2-mp4-avc"),
            GuardWindow(0x223D00, "2200805203008052e503022a44018052", "pre L2-mp4-hevc"),
            GuardWindow(0x223D20, "024400b9221040b9034c00b903008052", "post L2-mp4-hevc"),
            GuardWindow(0x2260B0, "f8ffff1701008252010ea1721f00016b", "pre L4-play"),
            GuardWindow(0x2260E0, "5f0000b9c0035fd6232c407920284079", "post L4-play"),
            GuardWindow(0x254100, "80ba407901008012bf630239a07300b9", "pre L3-nrt"),
            GuardWindow(0x254120, "bfa30239a0e30139804a40b9bfaf00b9", "post L3-nrt"),
        ),
    ),
    "fx3_702": BodySpec(
        body_id="fx3_702",
        camera="Sony ILME-FX3 (FX3)",
        firmware="7.02",
        libmpr_sha256="9aeef3b9edb3d011c0c90cd2387b3a47bd3b506ebfa57be39ad1a9729771b57c",
        sites=(
            PatchSite("L2-mp4-avc", 0x21FF3C, "060e8152", "06408152"),
            PatchSite("L2-mp4-hevc", 0x220074, "060e8152", "06408152"),
            PatchSite("L2-lvl-avc", 0x21FB0C, "20040054", "22040054"),
            PatchSite("L2-lvl-hevc", 0x21FC68, "80030054", "82030054"),
            PatchSite("L3-nrt-vline", 0x25027C, "80be4079", "00408152"),
            PatchSite("L3-nrt-noasp", 0x250288, "20008052", "00008052"),
            PatchSite("L4-play-w", 0x222330, "01c08352", "01e08152"),
            PatchSite("L4-play-h", 0x222334, "011ca272", "0140a172"),
        ),
        guards=(
            GuardWindow(0x0, "7f454c46020101030000000000000000", "ELF64 magic"),
            GuardWindow(0x21FAF0, "2007005420058052c0035fd620504079", "pre L2-lvl-avc"),
            GuardWindow(0x21FB10, "00058052c0035fd6c2149e52202040b9", "post L2-lvl-avc"),
            GuardWindow(0x21FC50, "1f044071e0179f1a00cc0011c0035fd6", "pre L2-lvl-hevc"),
            GuardWindow(0x21FC70, "1f00026b200200541fe01071e1050054", "post L2-lvl-hevc"),
            GuardWindow(0x21FF20, "28668c52c82eac721500001422008052", "pre L2-mp4-avc"),
            GuardWindow(0x21FF40, "07e08152f7ffff172200805203008052", "post L2-mp4-avc"),
            GuardWindow(0x220060, "3e0000142200805203008052e503022a", "pre L2-mp4-hevc"),
            GuardWindow(0x220080, "2200805203008052e503022a44018052", "post L2-mp4-hevc"),
            GuardWindow(0x222320, "1f00016b6100005480008052f2ffff17", "pre L4-play"),
            GuardWindow(0x222340, "c0035fd65f0000b9c0035fd6232c4079", "post L4-play"),
            GuardWindow(0x25026C, "80ba407901008012bf630239a07300b9", "pre L3-nrt"),
            GuardWindow(0x250290, "a0e30139804a40b9bfaf00b9a07f00b9", "post L3-nrt"),
        ),
    ),
}


def verify_libmpr_bytes(data: bytes, spec: BodySpec, *, require_sha256: bool = True) -> dict:
    """Verify ELF header, SHA-256 (optional), guards, and site states in an in-memory libmpr.so buffer."""
    sha = hashlib.sha256(data).hexdigest()
    errors: list[str] = []
    if require_sha256 and sha != spec.libmpr_sha256:
        errors.append(f"SHA-256 mismatch: got {sha}, expected {spec.libmpr_sha256}")

    for guard in spec.guards:
        want = bytes.fromhex(guard.bytes_hex)
        got = data[guard.offset : guard.offset + len(want)]
        if got != want:
            errors.append(
                f"Guard mismatch at {hex(guard.offset)} ({guard.note}): "
                f"got {got.hex() or '<eof>'}, expected {want.hex()}"
            )

    site_states: list[dict] = []
    for site in spec.sites:
        old_b = bytes.fromhex(site.old_hex)
        new_b = bytes.fromhex(site.new_hex)
        got = data[site.offset : site.offset + len(old_b)]
        if got == old_b:
            state = "stock"
        elif got == new_b:
            state = "patched"
        else:
            state = "unknown"
            errors.append(
                f"Site {site.kind} at {hex(site.offset)} mismatch: got {got.hex() or '<eof>'}, "
                f"expected stock {site.old_hex} or patched {site.new_hex}"
            )
        site_states.append({"kind": site.kind, "offset": hex(site.offset), "state": state})

    distinct = {row["state"] for row in site_states}
    overall_state = next(iter(distinct)) if len(distinct) == 1 else "mixed"
    return {
        "ok": not errors,
        "body_id": spec.body_id,
        "camera": spec.camera,
        "firmware": spec.firmware,
        "sha256": sha,
        "overall_state": overall_state,
        "sites_checked": len(site_states),
        "guards_checked": len(spec.guards),
        "site_states": site_states,
        "errors": errors,
    }


def _selftest() -> None:
    for spec in BODY_SPECS.values():
        size = max(
            max(g.offset + len(g.bytes_hex) // 2 for g in spec.guards),
            max(s.offset + len(s.old_hex) // 2 for s in spec.sites),
        )
        # Ensure guard windows and patch sites never overlap on any body.
        guard_ranges = [(g.offset, g.offset + len(g.bytes_hex) // 2, g.note) for g in spec.guards]
        for s in spec.sites:
            s0, s1 = s.offset, s.offset + len(s.old_hex) // 2
            for g0, g1, note in guard_ranges:
                assert not (s0 < g1 and g0 < s1), f"{spec.body_id} overlap {s.kind} vs {note}"

        buf = bytearray(size)
        for g in spec.guards:
            b = bytes.fromhex(g.bytes_hex)
            buf[g.offset : g.offset + len(b)] = b
        for s in spec.sites:
            b = bytes.fromhex(s.old_hex)
            buf[s.offset : s.offset + len(b)] = b

        res_stock = verify_libmpr_bytes(bytes(buf), spec, require_sha256=False)
        assert res_stock["ok"] and res_stock["overall_state"] == "stock", res_stock

        for s in spec.sites:
            b = bytes.fromhex(s.new_hex)
            buf[s.offset : s.offset + len(b)] = b
        res_patched = verify_libmpr_bytes(bytes(buf), spec, require_sha256=False)
        assert res_patched["ok"] and res_patched["overall_state"] == "patched", res_patched

        bad = bytearray(buf)
        bad[spec.guards[-1].offset] ^= 0xFF
        res_bad = verify_libmpr_bytes(bytes(bad), spec, require_sha256=False)
        assert not res_bad["ok"] and res_bad["errors"], res_bad

        with tempfile.NamedTemporaryFile(suffix=".so") as tf:
            tf.write(buf)
            tf.flush()
            file_res = verify_libmpr_bytes(Path(tf.name).read_bytes(), spec, require_sha256=False)
            assert file_res["ok"]

    print(f"SELFTEST OK: verified {len(BODY_SPECS)} bodies (8 sites + 13 non-overlapping guards each)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--body", choices=sorted(BODY_SPECS), help="Camera firmware target")
    parser.add_argument("--libmpr", type=Path, help="Path to unpacked /usr/lib/libmpr.so")
    parser.add_argument("--allow-unhashed", action="store_true", help="Skip strict SHA-256 check")
    parser.add_argument("--selftest", action="store_true", help="Run offline self-tests")
    args = parser.parse_args()

    if args.selftest:
        _selftest()
        return 0
    if not args.body or not args.libmpr:
        parser.error("--body and --libmpr are required unless --selftest is given")

    spec = BODY_SPECS[args.body]
    res = verify_libmpr_bytes(args.libmpr.read_bytes(), spec, require_sha256=not args.allow_unhashed)
    print(
        f"[{res['body_id']}] ok={res['ok']} state={res['overall_state']} "
        f"sites={res['sites_checked']} guards={res['guards_checked']} sha256={res['sha256'][:16]}..."
    )
    if res["errors"]:
        for err in res["errors"]:
            print(f"  ERROR: {err}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
