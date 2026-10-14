#!/usr/bin/env python3
"""Generate the known-bad single-edit mutants of the good cam.py.

Each mutant is one deliberate editing mistake an agent could plausibly make,
applied to a copy of examples/good/cam.py.  The self-test proves the judge
catches every one of them.

Usage:
    python3 mutate.py <good_cam.py> <outdir>      # writes <outdir>/<name>.py
    python3 mutate.py --list                      # names + one-line reasons
"""
import sys
from pathlib import Path

# (name, [(old, new), ...]) -- single-edit mutants of examples/good/cam.py.
# `old` must match exactly once in the good file.
MUTANTS = {
    "no_tool_offset": [
        ('TOOL_OFFSET_SCALE = 1.0', 'TOOL_OFFSET_SCALE = 0.0'),
    ],
    "deep_pass": [
        ('STEPDOWN_MM = 2.0', 'STEPDOWN_MM = 6.0'),
    ],
    "rapid_into_stock": [
        ('PLUNGE_WORD = "G1"', 'PLUNGE_WORD = "G0"'),
    ],
    "swapped_arcs": [
        ('ISLAND_ARC_B = "G3"', 'ISLAND_ARC_B = "G2"'),
    ],
    "inch_mode": [
        ('UNITS_WORD = "G21"', 'UNITS_WORD = "G20"'),
    ],
    "wide_stepover": [
        ('STEPOVER_MM = 2.5', 'STEPOVER_MM = 7.2'),
    ],
    "hot_feed": [
        ('FEED_SCALE = 1.0', 'FEED_SCALE = 5.0'),
    ],
}


def apply(source, name):
    text = source
    for old, new in MUTANTS[name]:
        if text.count(old) != 1:
            raise SystemExit(f"mutate: pattern {old!r} for {name} matches "
                             f"{text.count(old)} times (expected 1)")
        text = text.replace(old, new)
    return text


def main():
    if sys.argv[1:] == ["--list"]:
        for name, subs in MUTANTS.items():
            print(f"{name}: {subs[0][0]!r} -> {subs[0][1]!r}")
        return
    if len(sys.argv) != 3:
        raise SystemExit(__doc__)
    src_path, outdir = Path(sys.argv[1]), Path(sys.argv[2])
    source = src_path.read_text(encoding="utf-8")
    outdir.mkdir(parents=True, exist_ok=True)
    for name in MUTANTS:
        (outdir / f"{name}.py").write_text(apply(source, name), encoding="utf-8")
    print(f"mutate: wrote {len(MUTANTS)} mutants to {outdir}")


if __name__ == "__main__":
    main()
