#!/usr/bin/env python3
"""Generate known-bad single-edit mutants of the good spice-filter artifact.

Each mutant is exactly one textual edit (one line replaced or inserted) of
examples/good/lpf4sk.cir.  Used by judge/selftest.sh to prove the judge
fails bad inputs.  Output: <outdir>/<name>.cir plus a summary line per
mutant naming the edit.
"""

import sys
from pathlib import Path

# (name, exactly-one-line substring edits of the good netlist)
# Replacements are (old_line, new_line) on unique full lines; additions
# are inserted lines.  Each mutant is exactly one edit.
REPLACEMENTS = [
    ("r-decade-up", "R1 in s1a 750", "R1 in s1a 7.5k"),
    ("c-decade-down", "C3 s2a out 680n", "C3 s2a out 68n"),
    ("off-series", "R2 s1a s1b 750", "R2 s1a s1b 740"),
    ("swap-nodes", "C1 s1a out1 120n", "C1 s1b out1 120n"),
    ("missing-ground", "C2 s1b 0 100n", "C2 s1b gnd0 100n"),
    ("opamp-gain", "E2 out 0 s2b 0 1", "E2 out 0 s2b 0 100"),
]

# (name, anchor line, line to insert before it, note)
INSERTIONS = [
    # extra resistor across stage 1: no mask damage, but the shape is no
    # longer the one the closed-form oracle recognizes -> must fail closed
    ("unrecognised-topology", "E1 out1 0 s1b 0 1",
     "Rbias s1a s1b 1meg",
     "parallel damping resistor: valid design, shape the oracle cannot "
     "verify"),
]

# (name, old substring, new substring) applied to one full line each
LINE_PATCHES = [
    ("swap-feedback", "C1 s1a out1 120n", "C1 s1a 0 120n"),
]


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: mutants.py <good.cir> <outdir>", file=sys.stderr)
        return 2
    good = Path(sys.argv[1]).read_text()
    lines = good.splitlines()
    outdir = Path(sys.argv[2])
    outdir.mkdir(parents=True, exist_ok=True)

    made = 0
    for name, old, new in REPLACEMENTS:
        hit = [i for i, ln in enumerate(lines) if ln == old]
        if len(hit) != 1:
            print(f"mutants: anchor line {old!r} not found exactly once",
                  file=sys.stderr)
            return 1
        mutated = list(lines)
        mutated[hit[0]] = new
        (outdir / f"{name}.cir").write_text("\n".join(mutated) + "\n")
        print(f"mutants: {name}.cir  edit: '{old}' -> '{new}'")
        made += 1

    # one inserted line, not a replacement
    idx = lines.index(".control")
    mutated = lines[:idx] + ['.include "helpers.inc"'] + lines[idx:]
    (outdir / "include-directive.cir").write_text("\n".join(mutated) + "\n")
    print("mutants: include-directive.cir  edit: +'.include \"helpers.inc\"'")
    made += 1

    for name, anchor, inserted, note in INSERTIONS:
        if inserted is None:
            continue  # handled via LINE_PATCHES below
        hit = [i for i, ln in enumerate(lines) if ln == anchor]
        if len(hit) != 1:
            print(f"mutants: anchor line {anchor!r} not found exactly once",
                  file=sys.stderr)
            return 1
        mutated = lines[:hit[0]] + [inserted] + lines[hit[0]:]
        (outdir / f"{name}.cir").write_text("\n".join(mutated) + "\n")
        print(f"mutants: {name}.cir  edit: +'{inserted}' ({note})")
        made += 1

    for name, old, new in LINE_PATCHES:
        hit = [i for i, ln in enumerate(lines) if ln == old]
        if len(hit) != 1:
            print(f"mutants: anchor line {old!r} not found exactly once",
                  file=sys.stderr)
            return 1
        mutated = list(lines)
        mutated[hit[0]] = new
        (outdir / f"{name}.cir").write_text("\n".join(mutated) + "\n")
        print(f"mutants: {name}.cir  edit: '{old}' -> '{new}'")
        made += 1

    print(f"mutants: wrote {made} mutants to {outdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
