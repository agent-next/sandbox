# T2 Receipt — gate G2: random differential testing vs the Python ISS

Everything below is pasted from real runs in this sandbox on 2026-10-14.
Working directory for all commands: `cookbook/fpga-agent-loop/judge/`.
Toolchain installed by `setup.sh` this session (all sha256 checks ok, same
pins as T1-RECEIPT.md). Elisions are marked `[...]` — nothing is paraphrased.

## 1. ISS unit check on the 40 rv32ui images (criterion 1)

`iss.py` is stdlib-only (`argparse`-free; imports only `os`, `sys`, and the
judge's own `memh.py`). It executes the SPEC ISA exactly: every RV32I
instruction minus FENCE.I/CSR, all load/store widths and signs, misaligned
load/store and misaligned jump/fetch -> trap, x0 hard-wired, FENCE = NOP,
store to 0x10000000 recorded as tohost and ends the run.

```
$ time (pass=0; fail=0; for h in tests/*.hex; do
    out=$(python3 iss.py run "$h" --max-steps 2000000)
    case "$out" in
      *"STATUS=PASS TOHOST=0x00000001"*) pass=$((pass+1));;
      *) fail=$((fail+1)); echo "FAIL $(basename $h): $out";;
    esac
  done; echo "ISS rv32ui: $pass/40 tohost==1, $fail failures")
ISS rv32ui: 40/40 tohost==1, 0 failures

real	0m1.172s
user	0m0.964s
sys	0m0.173s
```

**Result: 40/40.**

## 2. gen.py — seeded determinism and coverage (criterion 2)

Fixed seed -> byte-identical .hex; different seed -> different image:

```
$ python3 gen.py --seed 42 --count 1 --len 500 --out /tmp/g1.hex
$ python3 gen.py --seed 42 --count 1 --len 500 --out /tmp/g2.hex
$ sha256sum /tmp/g1.hex /tmp/g2.hex
41c48917728faf97f63c8b4311f5636d81ae5842851f97c50f5cc29b8a1c96b0  /tmp/g1.hex
41c48917728faf97f63c8b4311f5636d81ae5842851f97c50f5cc29b8a1c96b0  /tmp/g2.hex
$ python3 gen.py --seed 43 --count 1 --len 500 --out /tmp/g3.hex
$ sha256sum /tmp/g3.hex
0b736c1a3852b04e8f59d25ed4c5ce7448691d6eb4f83e62769548a8284d1714  /tmp/g3.hex
```

Decode-based coverage check of a generated program (all 37 SPEC
instructions + FENCE-as-NOP must appear; "??" marks an undecodable word):

```
coverage: 38/38 SPEC insns present; missing: none
??-decoded words: none
ISS on generated program: PASS tohost=1 steps=431
```

The deterministic coverage block (`gen.py: coverage_block`) additionally
guarantees in every program: every branch taken AND not taken including a
backward counter loop, JAL and JALR forward AND backward (flag-guarded, run
exactly twice), every load/store width and sign via both x0 and a nonzero
base register. The epilogue stores x1..x31 to the signature region
0x040..0x0BC then stores 1 to tohost. All generated accesses are aligned and
in-range by construction, and every branch/jump target is a real instruction
boundary, so a correct run always ends via tohost.

## 3. grade.sh G2 at SPEC defaults on the known-good control (criterion 3)

`--g2-count` exists for quick runs; default is the SPEC's 200 programs x 500
instructions. The G2 "SKIP (T2/T3)" line is replaced by a real gate.

```
$ time ./grade.sh ref/picorv32_cpu.v --seed 7 --json verdict_ref.json
== G0: lint (verilator -Wall; yosys proc; check -assert)
   G0: PASS
== building Verilator model (tb.cpp + picorv32_cpu.v)
   build OK
== G1: riscv-tests rv32ui (latency seed 7)
   G1: PASS (40/40)
== G2: random differential vs ISS (200 programs x 500 instrs, base seed 7)
      G2: 200/200 programs agree (ISS == DUT signature)
== G3: directed trap tests
   G3: PASS (6/6)
== G4: bus (random mem_ready latency 0-7, seeds 8 108 1016)
   seed 8: 40/40
   seed 108: 40/40
   seed 1016: 40/40
   G4: PASS
== G5: SKIP (T3)
== G6: perf benchmark: SKIP (T3) - not a gate
{
  "pass": true,
  "gates": {
    "G0": { "pass": true },
    "G1": { "pass": true, "detail": "40/40 tests pass" },
    "G2": { "pass": true, "detail": "200/200 random programs match the ISS (x1..x31 signature)" },
    "G3": { "pass": true, "detail": "6/6 trap tests pass" },
    "G4": { "pass": true, "detail": "all G1 tests pass under latency seeds 8,108,1016" },
    "G5": { "skipped": true, "reason": "synth gate lands in T3" },
    "G6": { "skipped": true, "reason": "perf report lands in T3 (not a gate)" }
  },
  "seed": 7,
  "wall_seconds": 19,
  "tool_versions": {
    "verilator": "Verilator 5.053 devel rev v5.052-222-gd234caafc (mod)",
    "yosys": "Yosys 0.69+154 (git sha1 30d62572e-dirty, Release, Clang /usr/bin/clang++ 21.1.8)"
  }
}
GRADE_EXIT=0

real	0m18.540s
user	0m21.681s
sys	0m1.832s
```

On a mismatch the gate prints the first differing register and the program
seed (see the mutant runs in section 5; the register-level line is emitted
by `g2check.py` when the DUT completes but the signature differs, and the
seed is always printed).

## 4. ISS-vs-picorv32 agreement: 1,000 random programs (criterion 4)

SPEC self-test requirement: the ISS is trusted as G2's oracle only after it
agrees with picorv32 on 1,000 random programs. Same machinery as G2
(`g2check.py`, per-program seeded mem_ready latency on the DUT, x1..x31
signature compare), driven directly at --count 1000 against the Verilator
sim built from `ref/picorv32_cpu.v` + `tb.cpp`:

```
$ verilator --cc --exe --build -j 2 --top-module cpu -Wno-fatal \
    -I$HOME/riscv-toolchain/picorv32 --Mdir obj_dir -CFLAGS "-O2" \
    -o sim_cpu ref/picorv32_cpu.v tb.cpp
[... build OK ...]
$ time python3 g2check.py --sim /tmp/g2build/obj_dir/sim_cpu \
    --seed 7 --count 1000 --len 500
   G2: 1000/1000 programs agree (ISS == DUT signature)

real	0m41.756s
user	0m39.015s
sys	0m2.278s
EXIT=0
```

**Result: 1000/1000 agree, 41.8 s wall.** Zero disagreements, so no
ISS/generator fix was needed on this criterion. (Two real bugs were fixed
while building T2, both caught before this run: the ISS's SLTIU compared
the raw 12-bit immediate unsigned instead of sign-extending it first —
rv32ui's sltiu test exposed it; and gen.py's label/offset math originally
counted labels as instructions, corrupting backward control flow — the ISS
itself exposed that generated programs trapped.)

## 5. G2 power test: mutants that pass G1 but are caught by G2 (criterion 5)

`mutants.py` now ships 6 single-edit mutants. The two G2-targeted ones both
attack the J-immediate decode — rv32ui's *executed* JALs are all short
forward jumps, so JAL-distance/direction corruption is invisible to G1 and
only G2's coverage block (backward JAL/JALR) plus the random filler expose
it. `bimm-sign-drop` is kept as the honest control: the same trick on the
*branch* immediate IS caught by G1, because the no-CSR riscv_test.h
FAIL/PASS macros do execute backward branches.

```
$ python3 mutants.py
wrote .../mutants_out/branch-flip/picorv32.v       (BEQ/BNE swapped - G1)
wrote .../mutants_out/wstrb-lane-drop/picorv32.v   (SW lane drop - G1)
wrote .../mutants_out/ignore-mem-ready/picorv32.v  (mem_ready ignored - G4)
wrote .../mutants_out/bimm-sign-drop/picorv32.v    (branch imm sign - G1)
wrote .../mutants_out/jal-sign-drop/picorv32.v     (JAL imm[20] -> 0 - G2)
wrote .../mutants_out/jal-imm-hi-zero/picorv32.v   (JAL imm[19:12] -> 0 - G2)
6 mutants written to .../mutants_out
```

### 5.1 jal-sign-drop (JAL sign bit forced to 0)

```
$ PICORV32_DIR=$PWD/mutants_out/jal-sign-drop ./grade.sh ref/picorv32_cpu.v --seed 7
   G0: PASS
   build OK
   G1: PASS (40/40)                       <- passes rv32ui
   G2: FAIL (first mismatch):
      G2: MISMATCH program seed=7000021: DUT 'RESULT TRAP TOHOST=0x00000000 CYCLES=847 FETCHES=108' but ISS PASS
      G2: 0/200 programs agree
   G2: FAIL                               <- caught by G2 on program 0
   G3: PASS (6/6)
   G4: PASS
GRADE_EXIT=1   (verdict wall_seconds=11)
```

### 5.2 jal-imm-hi-zero (JAL imm[19:12] forced to 0)

```
$ PICORV32_DIR=$PWD/mutants_out/jal-imm-hi-zero ./grade.sh ref/picorv32_cpu.v --seed 7
   G0: PASS
   build OK
   G1: PASS (40/40)                       <- passes rv32ui
   G2: FAIL (first mismatch):
      G2: MISMATCH program seed=7000021: DUT 'RESULT TRAP TOHOST=0x00000000 CYCLES=847 FETCHES=108' but ISS PASS
      G2: 0/200 programs agree
   G2: FAIL                               <- caught by G2 on program 0
   G3: PASS (6/6)
   G4: PASS
GRADE_EXIT=1   (verdict wall_seconds=10)
```

Both mutants corrupt the backward JAL in the coverage block (present in
every generated program): the corrupted immediate sends the jump ~1 MiB
away, the fetch leaves RAM, the memory model returns 0, and 0x00000000 is
an illegal opcode -> TRAP. Different edits, same observable signature.

### 5.3 bimm-sign-drop — honest control (caught by G1, not G2)

```
$ PICORV32_DIR=$PWD/mutants_out/bimm-sign-drop ./grade.sh ref/picorv32_cpu.v --seed 7
   G0: PASS
   build OK
   FAIL add: RESULT TRAP TOHOST=0x00000000 CYCLES=1119 FETCHES=163
   [... 33 more identical-shape FAIL lines]
   G1: FAIL (6/40)                        <- rv32ui DOES cover backward branches
   G3: PASS (6/6)
   G4: FAIL
GRADE_EXIT=1
```

### Power-test summary

| mutant           | G1     | G2              | G3   | G4   | exit | wall   |
|------------------|--------|-----------------|------|------|------|--------|
| jal-sign-drop    | 40/40  | FAIL (seed 7000021) | 6/6 | PASS | 1    | 11 s |
| jal-imm-hi-zero  | 40/40  | FAIL (seed 7000021) | 6/6 | PASS | 1    | 10 s |
| bimm-sign-drop   | 6/40   | (not reached)   | 6/6  | FAIL | 1    | 10 s |

G2 has demonstrated independent killing power: two single-edit mutants that
sail through all 40 rv32ui tests die on the first generated program.

## 6. What is left for T3

- G5 synthesis (yosys `synth_ecp5` + nextpnr-ecp5 `--85k --package CABGA381`,
  IO-reducing wrapper) and G6 CPI report.
- `mutants.py` extended to >= 20 mutants with survivors shown equivalent by
  yosys LEC.
- `selftest.sh` end-to-end (it currently drafts the full-spec flow).
