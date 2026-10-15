# SPEC — `cookbook/climate-glacier-model/`

An agent works on a real glaciology problem inside a disposable agent-next
sandbox: run a 100-year surface-mass-balance (SMB) sweep over a synthetic
glacier under three climate scenarios, and be graded by a judge it cannot
fool — an **analytic solution** of the same model, a **zero-melt negative
control**, and per-cell physical invariants — not by whether the script ran.

The model is a simplified, single-length-variable SMB/volume model in the
spirit of the OGGM "constant-mass-balance-gradient" flowline setup
(`Recinos et al. 2019`, doi:10.5194/gmd-12-909-2019). It is not OGGM and
claims no OGGM numbers: it is a closed-form-solvable caricature, chosen so
that the judge has exact math to compare against.

## Goal

Produce `model.py`, a deterministic sweep that, for each of three warming
scenarios, integrates the model below for 100 yearly steps, writes a CSV of
volume vs. year, draws a single figure with the three curves, and reports
the year each scenario first drops below 50 % of its year-0 volume.

## Non-goals

- Real glacier geometry, real climate data, real OGGM runs, ice dynamics
  (no flow, no calving, no sliding), mass conservation beyond the model
  below, or any attribution of the numbers to a real glacier.
- Spatial detail beyond the 1-D mask described here; no map projections,
  no DEM handling, no shapefiles.
- Physical calibration or forecast skill. The scenario anomalies are
  prescribed numbers, not projections.
- Optimality, performance, or code style beyond the determinism rules.

## The model (normative — this is what the judge computes too)

All units SI unless stated. Constants are fixed by this spec; the artifact
must not re-tune them.

| symbol | value | meaning |
|---|---|---|
| `B0` | 400 m | bed elevation at `x = 0` |
| `Bs` | 0.05 | bed slope (dimensionless); `b(x) = B0 - Bs*x` |
| `W` | 800 m | constant glacier width |
| `ELA0` | 2900 m | equilibrium-line altitude at `t = 0` |
| `S` | 0.08 yr⁻¹ | mass-balance gradient (constant with elevation) |
| `tau` | 15 yr | length response time |
| `kappa` | 200 m K⁻¹ | ELA sensitivity to temperature anomaly |
| `nx` | 751 | cells, `x_i = 10*i` m for `i = 0..750` |
| `Z_head` | 3200 m | head (top) surface elevation |
| `years` | 100 | yearly steps, `t = 0..100` |

**Scenario temperature anomaly** (degrees C, prescribed, not fitted):

    a(t) = a1 + (a2 - a1) * t / years        # linear ramp

| scenario | `a1` | `a2` | `gamma` = `kappa*a2` (m) |
|---|---|---|---|
| `rcp26` | 0.000 | 0.006 | 1.20 |
| `rcp45` | 0.000 | 0.010 | 2.00 |
| `rcp85` | 0.000 | 0.016 | 3.20 |

**State and update.** The state is one number, the length `L` (m). Cell
`i` is ice when `x_i < L`; the surface elevation of ice is `Z_head`, the
bed is `b(x_i)`, so thickness `h_i = Z_head - b(x_i)` — independent of
`L`. Volume is the mask sum over the domain:

    V(L) = W * sum_{i: x_i < L} (Z_head - b(x_i)) * dx / 1e9     [km^3]

`L(0) = L0 = 2*(Z_head - ELA0)/S = 7500 m`, so `V(0) = 1.8 km^3` exactly
in the continuum limit.

For each year `t = 0..years-1`, with `ELA(t) = ELA0 + kappa*a(t)` and
`L_eq(t) = 2*(Z_head - ELA(t))/S`:

    L(t+1) = L(t) + (L_eq(t) - L(t)) / tau

Explicit forward Euler at `dt = 1 yr`, single-threaded, in this order.

**Analytic reference (the judge's oracle).** With `gamma = kappa*a2` and
the linear ramp, the update above has the closed-form solution

    L_exact(t) = L0 - (2*gamma/S) * (t - tau*(1 - exp(-t/tau)))

which satisfies the recurrence exactly at every integer `t` (the `a1 = 0`
ramp makes `L_eq` linear in `t`, which is what makes the exponential
integral elementary). In the continuum limit the mask sum gives
`V_exact(t) = 0.5*S*W*L_exact(t)^2 / 1e9`. The judge uses these, **not**
the artifact's own trajectory, as the reference.

## Artifact

One directory containing at least:

- `model.py` — the sweep. Runs to completion in ≤ 180 s on 2 vCPU / 3 GB.
  Must import no third-party module outside `{numpy, matplotlib, csv, json,
  math, os, sys, argparse}` and must not write outside its output
  directory.
- `volumes.csv` — header `scenario,year,volume_km3`, one row per scenario
  per year, 303 data rows, `year` integers `0..100`, one row for every
  (scenario, year) pair, values finite and ≥ 0.
- `crossings.json` — `{"rcp26": {"year": <number|null>}, "rcp45": ...,
  "rcp85": ...}` where `year` is the first year at which the scenario's
  volume is ≤ 50 % of its year-0 volume, linearly interpolated between the
  two bracketing yearly samples, or `null` if it never crosses.
- `retreat.png` — one figure, all three scenarios, volume (km³) vs. year
  (yr) on labelled axes with a title and a legend naming the three
  scenarios, ≥ 900 px wide, ≥ 150 dpi.
- `run.json` — `{"scenarios": {...}, "model": {...}}`: for each scenario
  the constants used (`a1`, `a2`, `gamma`, `tau`, `S`, `kappa`, `ELA0`,
  `L0`) and the reported crossing year, plus a top-level `seed` integer.

The file the judge is pointed at is the artifact **directory**.

## Judge gates (`judge/grade.sh <artifact-dir> [--seed N] [--json out.json]`)

All gates are numeric and deterministic; the default seed is `20261015`.
Exit 0 only if every gate passes; on failure the verdict names the gate and
prints the offending numbers.

- **G1 artifact**: the four files above exist, `model.py` parses
  (`py_compile`), imports nothing outside the allow-list, and the CSV has
  exactly the 303 expected `(scenario, year)` rows with finite, non-negative
  volumes.
- **G2 determinism**: `model.py` run twice into two temp dirs with the same
  seed produces **byte-identical** `volumes.csv` and `crossings.json`. A
  run that is not reproducible fails.
- **G3 zero-melt control (negative control)**: `model.py` is re-run with
  the scenario anomalies forced to zero (`--zero-melt`, an option the
  artifact must provide). Under zero warming the ELA never moves, the
  glacier is exactly in balance, and **no volume may be lost**: for all
  three scenarios `V(t) == V(0)` within **1e-9 km³** relative, and every
  reported crossing year must be `null`. Any run that still shrinks under
  zero forcing fails — this is the hidden-state gate (a model that reads
  stale temperature, applies the anomaly twice, or clamps the mask
  wrongly loses mass here even when the warming runs look plausible).
- **G4 crossing years**: each scenario's reported crossing year must be
  within **±3 years** of the analytic reference computed from
  `L_exact(t)` and `V_exact(t)` (roots below). A scenario that never
  crosses must be reported `null`; a reference that never crosses must be
  reported `null`.
- **G5 final volumes**: for each scenario, `V(100)` from the CSV must be
  within **2 % relative** of `V_exact(100)`.
- **G6 shape**: at every year the CSV volume must be within **2 %** of
  `V_exact(t)` (not just the endpoint), monotone non-increasing for every
  warming scenario, and the mask-consistency check below must hold.
- **G7 figure**: `retreat.png` is a valid PNG ≥ 900 px wide, ≥ 150 dpi
  (from the PNG's own `pHYs` chunk), and ≥ 20 kB (an empty or 1-pixel plot
  fails). The three scenario labels must appear in the figure's own
  metadata or in the artifact's `run.json` legend list; the judge does not
  OCR the image and says so.

Reference values (default seed, `examples/good/`, for orientation only —
the judge recomputes them):

| scenario | crossing year (analytic) | `V(100)/V(0)` |
|---|---|---|
| `rcp26` | 88.181 | 0.435499 |
| `rcp45` | 58.633 | 0.187667 |
| `rcp85` | 41.517 | 0.008673 |

## Acceptance oracle (independent of "it ran")

1. **Analytic solution.** The judge derives `L_exact(t)` and
   `V_exact(t)` in closed form (above) from the SPEC constants and
   compares the artifact's CSV against them. It never reads the
   artifact's trajectory as its own reference.
2. **Zero-melt negative control.** G3 is a second, independent oracle: a
   physically forced no-change case with an exact expected answer
   (`V(t) = V(0)`). It is the gate that a plausible-looking but
   state-corrupting model cannot pass.
3. **Mask/volume consistency.** The judge re-derives the volume from the
   artifact's *own* length trajectory: it re-runs the model and checks
   `V(t)` equals the mask sum `W*sum h_i*dx` over the cells the artifact
   reports as ice, to **1e-9** relative. A volume computed by a different
   formula than the mask (e.g. a constant-width box, or `L` in km) fails
   here even if it happens to be close.
4. **Determinism.** G2 plus the self-test's byte-identical repeat.

The analytic comparison is a real, non-trivial check: the good artifact
deviates from the closed form by ~2.6e-3 relative at the worst year
(the mask sum and the continuum formula differ at the one-cell level), and
the gate allows 2 %. A single wrong constant, a swapped `tau`, or a
one-year off-by-one all exceed it — see `judge/mutants.py`.

## Self-test (`judge/selftest.sh`)

- The known-good example passes every gate.
- ≥ 5 known-bad artifacts, generated by `judge/mutants.py` as **single
  edits** of the good example, each fail ≥ 1 gate; the self-test names the
  gate that killed each one.
- Kill rate ≥ 90 % printed; exit non-zero below that, or with fewer than 5
  mutants.
- Determinism: two `grade.sh` runs on the good example with the same seed
  produce byte-identical verdict JSON except the `timing` key.

## Judge-integrity rule

The artifact is copied to a temp dir before grading; `judge/grade.sh`
compares the sha256 of the whole `judge/` tree before and after every grade
and fails closed if anything changed. The judge never imports the
artifact; it runs it as a subprocess with `-I`.

## Out of scope for the judge

- Anything the artifact claims in comments, READMEs or log lines.
- Whether the figure is *beautiful* (only that it is a real, labelled,
  sufficiently large plot).
- Physical realism beyond the model above.

## Tools (pinned by `judge/setup.sh`)

- `judge/setup.sh` installs the demo's Python dependencies (numpy,
  matplotlib) at **exact versions** into a venv under `$HOME`, from wheels
  whose sha256 is pinned in `judge/requirements.txt` (`pip --require-hashes`).
  Exact versions are recorded in `judge/VERSIONS.txt`.
- The **judge itself is stdlib-only** (CPython ≥ 3.10, pure-float math, no
  numpy): its oracle must not depend on the same library the artifact uses,
  so a numpy version difference can never change a verdict.
- No network access is needed at grade time; only `setup.sh` downloads.

## Hygiene

Public repo: no hostnames, internal paths, keys or key-shaped strings, and
no names of people or of other sandbox products anywhere in this demo.
The only third-party references are the cited papers in `README.md`.
