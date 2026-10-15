# T3 receipt — G5 synth, G6 perf, mutants, selftest

Run on a fresh agent-next sandbox (2 vCPU, 3 GB, Debian 12) at commit
12d5c6d, cloned with `git clone --depth 1 -b <branch>`; commands run from
`cookbook/fpga-agent-loop`:

    bash judge/setup.sh
    bash judge/selftest.sh --quick     # 100-program ISS cross-check
    bash judge/selftest.sh             # 1000-program ISS cross-check

| step | exit | wall |
|---|---|---|
| setup.sh | 0 | (toolchain download; network-bound) |
| selftest.sh --quick | 0 | 1705 s |
| selftest.sh (full) | 0 | 2137 s |

## setup.sh (tail)

```
Toolchain ready at /home/user/riscv-toolchain
  oss-cad-suite : 2026-09-27        (/home/user/riscv-toolchain/oss-cad-suite/bin)
  riscv gcc     : 15.2.0-1        (/home/user/riscv-toolchain/riscv-none-elf/bin)
  riscv-tests   : 7b68f7b91f827f8d94cc1c57ff123752c5c8f704
  picorv32      : ef203c2b0a3fb793280f5114941416c425c5b461       (picorv32.v sha256 0836050971b3c6cdd28ac3b1e5719a67fb645161912bef1e472e63995ceb0622)
```

## selftest.sh (full) — mutant kill table and summary

```
mutant kill table:
branch-flip              KILLED    (G1,G2,G4)  (63s)
wstrb-lane-drop          KILLED    (G1,G2,G4,G6)  (55s)
ignore-mem-ready         KILLED    (G1,G2,G4)  (46s)
bimm-sign-drop           KILLED    (G1,G2,G4,G6)  (41s)
jal-sign-drop            KILLED    (G2,G6)  (48s)
jal-imm-hi-zero          KILLED    (G2,G6)  (67s)
add-sub-swap             KILLED    (G1,G2,G4,G6)  (106s)
and-or-swap              KILLED    (G1,G2,G4)  (64s)
xor-and-swap             KILLED    (G1,G2,G4)  (75s)
sll-shr-swap             KILLED    (G2,G6)  (82s)
lts-unsigned             KILLED    (G1,G2,G4)  (71s)
sra-sign-drop            KILLED    (G1,G2,G4)  (77s)
imm-i-unsign             KILLED    (G1,G2,G4,G6)  (78s)
lb-unsign                KILLED    (G1,G2,G4)  (62s)
lh-unsign                KILLED    (G1,G2,G4)  (65s)
lui-shift-16             KILLED    (G1,G2,G4,G6)  (85s)
bimm-x2                  KILLED    (G1,G2,G4,G6)  (79s)
store-addr-plus4         KILLED    (G1,G2,G4,G6)  (95s)
load-addr-plus4          KILLED    (G1,G2,G4,G6)  (64s)
pc-plus8                 KILLED    (G1,G2,G3,G4,G6)  (71s)
drop-link-we             KILLED    (G1,G2,G4)  (47s)
drop-reg-we              KILLED    (G1,G2,G3,G4,G6)  (77s)
read-becomes-write       KILLED    (G1,G2,G4,G6)  (50s)
bge-cond-flip            KILLED    (G1,G2,G4)  (50s)
bgeu-cond-flip           KILLED    (G1,G2,G4)  (45s)
eq-ne-flip               KILLED    (G1,G2,G4)  (58s)
rs1-rs2-swap             KILLED    (G1,G2,G3,G4,G6)  (40s)
fence-undecoded          KILLED    (G1,G2,G4)  (38s)
trap-stuck-lo            KILLED    (G3,G5)  (18s)
ebreak-uncaught          SURVIVOR  (38s)
lw-misalign-blind        KILLED    (G1,G2,G4,G6)  (47s)
sb-lane-shift            KILLED    (G1,G2,G4)  (39s)
kill rate: 31/32 = 96.9%  (1942s)

--- step 5: LEC survivor proofs (SPEC recipe via lec.sh)
  ebreak-uncaught:
    LEC: EQUIVALENT (equiv_simple + equiv_induct proved every $equiv cell)
    -> proven equivalent (survivor accepted)

--- step 6: LEC power check (same recipe on a known-killed mutant)
  lec.sh on killed mutant: branch-flip
  LEC: NOT EQUIVALENT (sat found trigger=1 model)
  LEC power check: PASS (recipe detects a real difference)
(34s for steps 5-6)

=== SELFTEST: PASS ===
  control picorv32: PASS (G0-G5)
  control metrics:  LUT4=1458 FF=451 Fmax=87.18 MHz CPI=3.7707
  iss x-check:      1000/1000 programs agree
  mutants:          31/32 killed (96.9%)
  survivors proven: ebreak-uncaught
  LEC power check:  PASS (branch-flip -> NOT EQUIVALENT)
  wall time:        2137s
```

## selftest.sh --quick — summary

```
=== SELFTEST: PASS ===
  control picorv32: PASS (G0-G5)
  control metrics:  LUT4=1458 FF=451 Fmax=87.18 MHz CPI=3.7707
  iss x-check:      100/100 programs agree
  mutants:          31/32 killed (96.9%)
  survivors proven: ebreak-uncaught
  LEC power check:  PASS (branch-flip -> NOT EQUIVALENT)
  wall time:        1705s
```

## Notes

- `ebreak-uncaught` survives simulation (EBREAK traps are not observed by
  the G1/G2 programs) and is accepted only because the bounded LEC recipe
  in `lec.sh` proves it equivalent; the same recipe on the killed mutant
  `branch-flip` reports NOT EQUIVALENT (power check).
- Deviations: the T3 builder agent ran out of time before running the
  selftests; these runs were made by the lead from a fresh sandbox.
