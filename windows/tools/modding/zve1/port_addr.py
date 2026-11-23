"""Port data addresses of one build's cpapp-b.bin to another's through the code that builds them (2026-11-24, ZV-E1 port).

  python -B port_addr.py <src_build> <dst_build> <addr> [<addr> ...] [--refs N] [--slack N]

For each source address: the MOVW/MOVT pairs that build it (find_movw.pairs, within --slack bytes below it, default 0) are
the references. The code around each reference is found in the destination by voting (match_seed.vote); the two
stretches are disassembled and aligned (diff_consts.listing), and the constant at the aligned instruction is the
destination's counterpart. Each reference votes for one destination address; the result lists every candidate with its
votes, so a disagreement is visible. Up to --refs references (default 6) are used per address.

Read-only. A help for porting: every address that a design writes must still be checked against the table's contents.
"""
import argparse
import difflib
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import diff_consts  # noqa: E402
import find_movw  # noqa: E402
import locate_file  # noqa: E402
import match_seed  # noqa: E402


def refs(img, addr, slack=0):
    return [(code, val) for val, code, _reg in find_movw.pairs(img, addr - slack, addr + 1)]


def port_one(a, b, addr, nrefs=6, slack=0):
    votes, notes = Counter(), []
    for code, val in refs(a, addr, slack)[:nrefs]:
        start = max(code - 64, 0x108000) & ~1
        c = match_seed.vote(a, b, start, span=320, seed=10)
        if not c:
            notes.append(f"{code:#x}: no code match")
            continue
        delta, n = c[0]
        la = diff_consts.listing(a, start, 200)
        lb = diff_consts.listing(b, start + delta, 200)
        sm = difflib.SequenceMatcher(None, [x[1] for x in la], [x[1] for x in lb], autojunk=False)
        got = None
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag != "equal":
                continue
            for x, y in zip(la[i1:i2], lb[j1:j2]):
                if x[2] == val and y[2] is not None and x[0] >= code - 8:
                    got = y[2] + (addr - val)
                    break
            if got is not None:
                break
        if got is None:
            notes.append(f"{code:#x} -> {code + delta:#x} ({n} votes): value not aligned")
        else:
            votes[got] += 1
            notes.append(f"{code:#x} -> {code + delta:#x} ({n} votes): {got:#x}")
    return votes, notes


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src")
    ap.add_argument("dst")
    ap.add_argument("addr", nargs="+")
    ap.add_argument("--refs", type=int, default=6)
    ap.add_argument("--slack", type=lambda s: int(s, 0), default=0)
    ap.add_argument("-v", action="store_true", help="print every reference's outcome")
    args = ap.parse_args()
    a = locate_file.locate(args.src, "cpapp-b.bin").read_bytes()
    b = locate_file.locate(args.dst, "cpapp-b.bin").read_bytes()
    for s in args.addr:
        addr = int(s, 16)
        votes, notes = port_one(a, b, addr, args.refs, args.slack)
        best = ", ".join(f"{k:#x} ({v})" for k, v in votes.most_common(3)) or "none"
        print(f"{addr:#x} -> {best}")
        if args.v:
            for n in notes:
                print("    " + n)


if __name__ == "__main__":
    main()
