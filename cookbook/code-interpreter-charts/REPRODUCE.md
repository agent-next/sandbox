# REPRODUCE — independent reproduction of `code-interpreter-charts`

Date: 2026-10-15. Run by a different agent than the demo's author, following
only `README.md`'s "One-command run", from `/home/user/w` (branch
`sbx/demo-code-interpreter-charts-f4`). Exit code 0; total wall ~5 m 13 s
(313 s). `run.py` created and killed the sandbox itself.

How it was run (one line): `python3 cookbook/code-interpreter-charts/run.py --ref sbx/demo-code-interpreter-charts-f4`

## Results (verbatim from this run's output)

| step | wall | exit |
| --- | --- | --- |
| `sbx create --timeout-min 30` | 6.3 s | 0 |
| `git clone` (depth 1, pinned ref) | 8.4 s | 0 |
| `judge/setup.sh` (cold) | 111.0 s | 0 |
| `judge/selftest.sh` | 166.3 s | 0 |
| `judge/grade.sh examples/good` | 13.7 s | 0 |

Verdict: `"passed": true`, `failed_gate: null`, seed 20261015.

| answer | got | RECEIPT | match (1e-6 rel) |
| --- | --- | --- | --- |
| `mauna_loa_trend_ppm_per_year` | 2.098461926597848 | 2.098461926597848 | yes (abs_diff 4.44e-16) |
| `mauna_loa_seasonal_amplitude_ppm` | 5.833611111111111 | 5.833611111111111 | yes (abs_diff 0.0) |
| `mauna_loa_mean_annual_growth_ppm` | 2.0827619047619024 | 2.0827619047619024 | yes (abs_diff 0.0) |
| `owid_world_emissions_2024_gt` | 37.398064855 | 37.398064855 | yes (abs_diff 0.0) |
| `owid_top_emitter_2024_share` | 0.3286008794210911 | 0.3286008794210911 | yes (abs_diff 0.0) |

G3 plot-area variance: C1 265.112, C2 3627.816, C3 708.761 (threshold ≥ 50).
G4: 432 points / 12 months / top-10, top entity China. G5 PNG bytes:
99321 / 28663 / 35604. `artifact_run_s` = 6.768. Self-test kill rate:
**12/12 = 100 %** (same twelve kills as RECEIPT), determinism OK.

```text
run: SUMMARY passed=True trend=2.098461926597848 ppm/yr amplitude=5.833611111111111 ppm total=37.398064855 Gt C2_plot_var=3627.816 artifact_run=6.768s
run: killed and confirmed gone: 01a14012-b0d5-75f1-a731-afbad84709a1
RUN_EXIT_CODE=0
```

## Match / mismatch vs RECEIPT.md

- Five G2 answers: **match** RECEIPT's two runs exactly, well inside the
  1e-6 relative tolerance (largest diff 4.44e-16, on the OLS trend).
- Kill rate: **match** — 12/12 = 100 %, same mutants, same gates.
- G4 and G5: **match** byte-for-byte (432/12/10, China; 99321/28663/35604).
- G3 plot-area variances: **match to ~0.1–0.3 %** — 265.112 / 3627.816 /
  708.761 here vs 265.025 / 3634.153 / 707.972. All far above the threshold
  of 50; the deltas are PNG rendering nondeterminism across machines, not a
  data difference.
- `passed`: **match** — true. No mismatches.

## Deviations

- Wall times: this sandbox was faster on CPU-bound steps (`artifact_run_s`
  6.768 vs 13.178–14.365; selftest 2 m 46 s vs 2 m 59 s – 4 m 21 s); grade
  13.7 s and cold setup 1 m 51 s sit inside RECEIPT's ranges. README warns
  wall times vary ~2×; the numbers, not the times, are the stable part.
- The local checkout had uncommitted edits (`judge/selftest.sh`, `media/`);
  the run clones the pinned ref fresh, so they did not affect it. No step
  failed; nothing was run by hand in the sandbox.
