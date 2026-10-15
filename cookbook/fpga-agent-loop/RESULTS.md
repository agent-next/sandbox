# Leaderboard: agent-designed RV32I CPUs

Each designer model got the same prompt (SPEC.md interface, judge kit in
`judge/`) and one sandbox session to write `designs/<model>/cpu.v`. The
designs were then re-graded by the lead in a fresh sandbox with a seed the
designers never saw:

    bash judge/grade.sh <cpu.v> --seed 90210 --json results/<name>.json

| design | G0 lint | G1 ISA | G2 diff | G3 trap | G4 bus | G5 synth | overall | LUT4 | FF | Fmax (MHz) | CPI (G6) |
| --- | --- | --- | --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: |
| picorv32 (reference control) | pass | pass | pass | pass | pass | pass | **PASS** | 1458 | 451 | 87.18 | 3.77 |
| glm-5.3 | pass | pass | pass | pass | pass | pass | **PASS** | 11779 | 93 | 31.81 | 1.31 |
| devin swe-2 | pass | fail | fail | pass | fail | pass | FAIL | 12989 | 77 | 29.94 | 1.31 |
| longcat-2.5 | pass | fail | fail | fail | fail | pass | FAIL | 2456 | 1188 | 50.87 | 216.76 |

- glm-5.3 passes every gate on the hidden seed, at 2.9x fewer cycles per
  instruction than picorv32 but 8x the LUTs and 37 % of its Fmax.
- devin swe-2 passes 37/40 rv32ui tests; lui, sra and srai fail (tohost=7), and G2
  finds the same class of mismatch. Its session was stopped by the lead
  after about 70 minutes; the design is graded as left.
- longcat-2.5 lints and synthesizes, but every rv32ui test times out without
  writing tohost (`RESULT TIMEOUT ... CYCLES=400000`): the core never
  retires a test.
- Two more designers (step-5, pro-open) produced no design: their provider
  returned rate-limit and model-retired errors for the whole session.

Raw verdicts: `results/*.json`.
