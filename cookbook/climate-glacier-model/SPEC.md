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
the judge has exact math to compare against.

## Goal

Produce `model.py`, a deterministic sweep that, for each of three warming
scenarios, integrates the model below for 100 yearly steps, writes a CSV of
volume vs. year, draws a single figure with the three curves, and reports
the year each scenario first drops below 50 % of its year-0 volume.

## Non-goals

- Real glacier geometry, real climate data, real OGGM runs, ice dynamics
  (no flow, no calving, no sliding), or any attribution of the numbers to a
  real glacier.
- Spatial detail beyond the 1-D mask below; no map projections, DEMs or
  shapefiles.
- Physical calibration or forecast skill. The scenario anomalies are
  prescribed numbers, not projections.
- Optimality, performance, or code style beyond the determinism rules.

## The model (normative — the judge computes exactly this too)

SI units. These constants are fixed by this spec; the artifact must not
re-tune them.

| symbol | value | meaning |
|---|---|---|
| `Z_HEAD` | 3500 m | head (top) surface elevation; the ice surface is flat |
| `SLOPE` | 0.08 | bed slope; bed `b(x) = Z_HEAD - SLOPE*x` |
| `H0` | 650 m | ice thickness at `x = 0`; `h(x) = H0 - DH*x` |
| `DH` | 0.02 | thickness taper (dimensionless) |
| `W` | 800 m | constant glacier width |
| `ELA0` | 2900 m | equilibrium-line altitude at `t = 0` |
| `KAPPA` | 200 m K⁻¹ | ELA sensitivity to the temperature anomaly |
| `TAU` | 10 yr | length response time |
| `DX` | 25 m | cell size; `x_i = DX*(i+0.5)`, `i = 0..NX-1` |
| `NX` | 800 | cells; the domain is 20 km, the ice 15 km at `t = 0` |
| `YEARS` | 100 | yearly steps, `t = 0..100` |

Note `h(x) = Z_HEAD - b(x) - DH*x`: the ice surface is flat at `Z_HEAD`,
the bed falls at `SLOPE`, and the thickness tapers a further `DH` per
metre. The taper is what makes volume a *concave* function of length, so
the analytic volume below is a trapezoid and not a box.

**Scenario temperature anomaly** (degrees C, prescribed, not fitted):

    a(t) = a2 * t / YEARS

| scenario | `a2` (K at year 100) | `ELA(YEARS)` (m) |
|---|---|---|
| `warm_2p0` | 2.0 | 3300 |
| `warm_2p4` | 2.4 | 3380 |
| `warm_2p8` | 2.8 | 3460 |

**State and update.** The state is one number, the length `L` (m). Cell
`i` is ice when `x_i < L`. Volume is the mask sum over the domain:

    V(L) = W * sum_{i: x_i < L} h(x_i) * DX / 1e9     [km^3]

`L(0) = L0 = 2*(Z_HEAD - ELA0)/SLOPE = 15000 m`, giving `V(0) = 6.0 km^3`
(the cell-centre sum equals the trapezoid `W*(H0*L0 - DH*L0^2/2)/1e9`
exactly for this cell layout).

For each year `t = 0..YEARS-1`, with `ELA(t) = ELA0 + KAPPA*a(t)` and

    L_eq(t) = 2*(Z_HEAD - ELA(t))/SLOPE = L0 - (2*KAPPA/SLOPE)*a(t)

the update is

    L(t+1) = L(t) + (L_eq(t) - L(t)) / TAU

Explicit forward Euler at `dt = 1 yr`, single-threaded, in this order.

**Analytic reference (the judge's oracle).** The ramp makes `L_eq` linear
in `t`, so the recurrence has the closed-form solution

    L_exact(t) = L0 - (2*KAPPA/SLOPE)*a2*(t/YEARS - (TAU/YEARS)*(1 - exp(-t/TAU)))

which satisfies the recurrence at every integer `t` and carries the exact
relaxation transient. The judge compares against
`V_exact(t) = W*(H0*L_exact(t) - DH*L_exact(t)^2/2)/1e9` and the crossing
root of that, never against the artifact's own trajectory.

## Artifact

One directory containing at least:

- `model.py` — the sweep. Runs in ≤ 180 s on 2 vCPU / 3 GB. Imports
  nothing outside `{numpy, matplotlib, csv, json, math, os, sys, argparse}`;
  writes only inside its output directory; accepts `--out DIR`,
  `--seed N` and `--zero-melt`.
- `volumes.csv` — header `scenario,year,volume_km3`, exactly 303 data rows:
  one for every `(scenario, year)` pair, `year` integers `0..100`, volumes
  finite and ≥ 0.
- `crossings.json` — `{"warm_2p0": {"year": <number|null>, "volume_km3":
  <number>}, ...}`; `year` is the first year at which volume is ≤ 50 % of
  that scenario's year-0 volume, linearly interpolated between the two
  bracketing yearly samples, or `null` if it never crosses.
- `retreat.png` — one figure, all three scenarios, volume (km³) vs. year
  (yr), labelled axes, title, legend naming the three scenarios, ≥ 900 px
  wide, ≥ 150 dpi.
- `run.json` — `{"seed": <int>, "scenarios": {...}, "model": {...}}`: the
  `seed`, per-scenario constants used (`a2`, `ELA_at_year_100`, `L0`,
  `crossing_year`) and the shared model constants.

The artifact the judge is pointed at is the artifact **directory**.

## Judge gates (`judge/grade.sh <artifact-dir> [--seed N] [--json out.json]`)

All numeric and deterministic; default seed `20261015`. Exit 0 only if
every gate passes; on failure the verdict names the gate and prints the
offending numbers.

- **G1 artifact**: the five files exist, `model.py` compiles
  (`py_compile`), imports nothing outside the allow-list, and the CSV has
  exactly the 303 expected `(scenario, year)` rows with finite,
  non-negative volumes.
- **G2 determinism**: `model.py` run twice into two temp dirs with the same
  seed produces **byte-identical** `volumes.csv` and `crossings.json`.
- **G3 zero-melt control (negative control)**: `model.py` is re-run with
  `--zero-melt`. With no warming the ELA never moves, the glacier is
  exactly in balance, and **no volume may be lost**: for all three
  scenarios every year's volume equals `V(0)` to within **1e-9 km³**, and
  every crossing year must be `null`. A model that still shrinks here has
  hidden state — a stale temperature, an anomaly applied twice, a mask
  clamped wrongly — and fails even when its warming runs look plausible.
- **G4 crossing years**: each reported crossing year must be within
  **±3 years** of the analytic reference root. A scenario that never
  crosses must be reported `null`, and a reference that never crosses must
  be reported `null`.
- **G5 final volumes**: each scenario's `V(100)` must be within **2 %
  relative** of `V_exact(100)`.
- **G6 shape**: at *every* year the CSV volume must be within **2 %** of
  `V_exact(t)` (not just the endpoint), every warming scenario must be
  monotone non-increasing, and the mask-consistency check below must hold.
- **G7 figure**: `retreat.png` is a valid PNG, ≥ 900 px wide, ≥ 150 dpi
  (read from its own `pHYs` chunk), ≥ 20 kB, and the three scenario names
  appear in the artifact's `run.json` legend list. The judge does not OCR
  the image and says so in the verdict.

Reference values for `examples/good/` (default seed; the judge recomputes
them, they are listed for orientation):

| scenario | `a2` | crossing year (analytic) | crossing year (measured) | `V(100)/V(0)` |
|---|---|---|---|---|
| `warm_2p0` | 2.0 | 96.007 | 96.008 | 0.472000 |
| `warm_2p4` | 2.4 | 81.670 | 81.606 | 0.340480 |
| `warm_2p8` | 2.8 | 71.426 | 71.406 | 0.200320 |

## Acceptance oracle (independent of "it ran")

1. **Analytic solution.** The judge derives `L_exact(t)`, `V_exact(t)` and
   the crossing roots in closed form (above) from the SPEC constants and
   compares the CSV against them. It never reads the artifact's own
   trajectory as its reference.
2. **Zero-melt negative control.** G3 is a second, independent oracle: a
   forced no-change case whose exact answer is `V(t) = V(0)`. It is the
   gate a plausible-looking but state-corrupting model cannot pass.
3. **Mask/volume consistency.** The judge re-derives volume from the
   artifact's *own* length trajectory: it runs the model once more with an
   instrumented import-free replay of the mask sum and requires `V(t)` to
   equal `W*sum_{x_i<L} h(x_i)*DX` to **1e-9** relative. A volume computed
   by a different formula — a constant-width box, `L` in km, the wrong
   taper — fails here even if the endpoint happens to be close.
4. **Determinism.** G2, plus the self-test's byte-identical repeat.

The analytic comparison is non-trivial: the good artifact deviates from the
closed form by at most **3.8e-3** relative across all years (the cell
mask and the continuum trapezoid differ at the one-cell level), and the
gate allows 2 %. A wrong constant, a swapped `TAU`, or a one-year
off-by-one each exceed it — see `judge/mutants.py`.

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
artifact; it runs it as a subprocess with `python3 -I`.

## Out of scope for the judge

- Anything the artifact claims in comments, READMEs or log lines.
- Whether the figure is *beautiful* — only that it is a real, labelled,
  sufficiently large plot. The judge cannot read pixels; it says so.
- Physical realism beyond the model above.

## Tools (pinned by `judge/setup.sh`)

- `judge/setup.sh` installs the demo's Python dependencies (numpy,
  matplotlib) at **exact versions** into a venv under `$HOME`, from wheels
  whose sha256 is pinned in `judge/requirements.txt`
  (`pip --require-hashes`). The exact versions land in `judge/VERSIONS.txt`.
- The **judge itself is stdlib-only** (CPython ≥ 3.10, pure-float math, no
  numpy): its oracle must not share a library with the artifact, so a
  numpy version difference can never change a verdict.
- Only `setup.sh` downloads anything; grading needs no network.

## Hygiene

Public repo: no hostnames, internal paths, keys or key-shaped strings, and
no names of people or of other sandbox products anywhere in this demo. The
only third-party references are the cited papers in `README.md`.
