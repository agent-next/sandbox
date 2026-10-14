# Known-bad artifacts (mutants)

These are generated, not stored: `judge/mutants.py` writes each one as a
single edit of `examples/good`, and `judge/selftest.sh` requires the good
artifact to pass and >= 90 % of these to fail at least one gate.

Kill lines below are from the real selftest output in RECEIPT.md
(fresh-setup run 1, 2026-10-14; identical in run 2).

| # | mutant | edit vs good | killed by gate | kill line (real selftest output) |
|---|---|---|---|---|
| 1 | `units-in-metres` | all dimensions written in metres instead of mm | spec_limits | `units-in-metres: FAIL (expected) -- killed by gate: spec_limits` |
| 2 | `propped-tip` | extra clamp `NTIP, 3, 3` props the tip (wrong BC) | verification, convergence, spec_limits | `propped-tip: FAIL (expected) -- killed by gate: verification, convergence, spec_limits` |
| 3 | `load-on-ntip` | -250 N on every tip-face node instead of the 4 corner nodes | verification, convergence, spec_limits | `load-on-ntip: FAIL (expected) -- killed by gate: verification, convergence, spec_limits` |
| 4 | `coarse-mesh` | `mesh_size` = min(b,h) (fewer than 2 elements across the width) | verification, convergence, spec_limits | `coarse-mesh: FAIL (expected) -- killed by gate: verification, convergence, spec_limits` |
| 5 | `unconverged` | b=30, h=60, mesh_size=15 — legal but not mesh-converged | convergence | `unconverged: FAIL (expected) -- killed by gate: convergence` |
| 6 | `load-wrong-dof` | load in +Y (dof 2) instead of -Z (dof 3) | verification, convergence, spec_limits | `load-wrong-dof: FAIL (expected) -- killed by gate: verification, convergence, spec_limits` |
| 7 | `overload-10x` | -2500 N per corner node = 10x the spec load | spec_limits | `overload-10x: FAIL (expected) -- killed by gate: spec_limits` |
| 8 | `undersized` | b=8, h=40 — stress and deflection exceed the spec | spec_limits | `undersized: FAIL (expected) -- killed by gate: spec_limits` |
| 9 | `no-stress-output` | `*EL FILE ... S` output request removed from the deck | verification, convergence, spec_limits | `no-stress-output: FAIL (expected) -- killed by gate: verification, convergence, spec_limits` |

Kill rate: **9/9 (100 %)** in both fresh-setup runs.

Which gate catches which defect is not incidental:

- `units-in-metres`, `overload-10x`, `undersized` — quantities are finite
  but wrong, so only the **spec_limits** comparisons against the
  Euler-Bernoulli oracle and the fixed allowable/limit catch them.
- `propped-tip`, `load-on-ntip`, `load-wrong-dof`, `no-stress-output` —
  broken BCs/load/output would corrupt every solve, so the
  **verification** gate on the fixed reference beam fails first.
- `unconverged` — a legal design whose two meshes disagree; only the
  **convergence** gate can see it.
- `coarse-mesh` — rejected up front by the mesh-size validation, failing
  all gates.

No gate passes merely because `ccx` ran: each compares against an
independent oracle (Euler-Bernoulli theory, the spec mask, or the
refined-mesh convergence check).
