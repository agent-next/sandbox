#!/usr/bin/env python3
"""Generate single-edit mutants of the fetched picorv32.v (judge power test).

Each mutant is a (name, search, replace) edit applied to a fresh copy of
$HOME/riscv-toolchain/picorv32/picorv32.v; the SPEC-interface wrapper
judge/ref/picorv32_cpu.v then includes the mutated file via the
PICORV32_DIR_OVERRIDE include path. grade.sh must FAIL every mutant on at
least one gate - a surviving mutant means the judge is too weak (or the
edit is a semantic no-op, which must be shown equivalent).

T1 ships the three mandatory mutants (branch flip, dropped wstrb lane,
ignored mem_ready). T3 extends this list to >= 20.

Usage:
    mutants.py            write mutants to mutants_out/<name>/picorv32.v
    mutants.py --list     print the mutant table

Grading a mutant (each dir shadows the include path so the SPEC wrapper
picks up the mutated core):
    PICORV32_DIR=$PWD/mutants_out/<name> ./grade.sh ref/picorv32_cpu.v
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "mutants_out")
PICO_V = os.path.join(os.path.expanduser("~"),
                      "riscv-toolchain", "picorv32", "picorv32.v")

# (name, search, replace, why it must be caught)
MUTANTS = [
    (
        "branch-flip",
        """		case (1'b1)
			instr_beq:
				alu_out_0 = alu_eq;
			instr_bne:
				alu_out_0 = !alu_eq;""",
        """		case (1'b1)
			instr_beq:
				alu_out_0 = !alu_eq;
			instr_bne:
				alu_out_0 = alu_eq;""",
        "BEQ/BNE conditions swapped: rv32ui branch tests must fail (G1)",
    ),
    (
        "wstrb-lane-drop",
        "mem_la_wstrb = 4'b1111;",
        "mem_la_wstrb = 4'b0111;",
        "SW drops byte lane 0: every full-word store corrupts memory (G1)",
    ),
    (
        "ignore-mem-ready",
        "assign mem_xfer = (mem_valid && mem_ready) || (mem_la_use_prefetched_high_word && mem_do_rinst);",
        "assign mem_xfer = (mem_valid) || (mem_la_use_prefetched_high_word && mem_do_rinst);",
        "mem_ready ignored: only survives if the tb never stretches a "
        "request - G4's random latency must break it",
    ),
]


def load_reference():
    with open(PICO_V) as f:
        return f.read()


def apply_edit(src, search, replace):
    if src.count(search) != 1:
        raise SystemExit(
            "edit anchor not unique (%d hits) - pin drifted?" % src.count(search))
    return src.replace(search, replace)


def main(argv):
    if "--list" in argv:
        for name, _, _, why in MUTANTS:
            print("%-20s %s" % (name, why))
        return 0
    os.makedirs(OUT_DIR, exist_ok=True)
    src = load_reference()
    for name, search, replace, why in MUTANTS:
        mdir = os.path.join(OUT_DIR, name)
        os.makedirs(mdir, exist_ok=True)
        out = os.path.join(mdir, "picorv32.v")
        with open(out, "w") as f:
            f.write(apply_edit(src, search, replace))
        print("wrote %s  (%s)" % (out, why))
    print("%d mutants written to %s" % (len(MUTANTS), OUT_DIR))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
