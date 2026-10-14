# SPEC — rf-openems: 2.45 GHz microstrip patch antenna, judged by FDTD

## Goal

An agent designs (or repairs) a **2.45 GHz probe-fed microstrip patch antenna
on FR-4** inside a disposable agent-next sandbox. The deliverable is a
parameterised Python script driving **openEMS** (3-D cartesian FDTD). A judge
the agent cannot modify runs the simulation itself and checks the result
against numeric gates plus an independent analytic oracle.

## Tooling

openEMS 0.0.35 (Debian bookworm package `python3-openems`, exact version +
sha256 pinned, extracted into `$HOME` without root — see `judge/setup.sh` and
`judge/packages.txt`). openEMS is the required solver per the demo brief; it
is not on PyPI or conda-forge, so the pinned Debian package is the pinned
source of truth.

## Non-goals

- Gain/efficiency/far-field pattern — only the driving-point (S11) spec
  counts. nf2ff is disabled.
- Broadband design (2.2–2.7 GHz sweep is enough).
- Arrays, feed networks, dual-band.
- Production mesh-convergence study — the judge requires one coarse→fine
  *confirmation run*, documented, not an asymptotic study.

## The artifact

`antenna.py` — a self-contained Python script with:

1. A **top-of-file parameter block** of literal constants (AST-parseable;
   names, units as given):
   ```
   f_target_ghz = 2.45    # GHz
   er           = 4.4     # substrate permittivity
   tanD         = 0.02    # substrate loss tangent
   sub_h        = 1.6     # mm  substrate thickness
   patch_L      = 27.6    # mm  resonant length
   patch_W      = 37.0    # mm
   feed_inset   = 8.0     # mm  probe inset from the radiating edge
   mesh_res     = 1.2     # mm  max mesh step inside the substrate footprint
   ```
2. `def simulate(p, sim_path) -> {"freqs_GHz": [...], "S11_dB": [...]}` —
   builds the geometry, runs openEMS into `sim_path` (which must afterwards
   contain the raw port files `port_ut_1` / `port_it_1`), and returns the
   S11 sweep over 2.2–2.7 GHz (>= 21 points).
3. When run as `__main__`, it calls `simulate()` with the parameter block,
   writes `antenna_results.json` in the current directory
   (`{"S11_dB_at_target", "f_res_GHz", "freqs_GHz", "S11_dB"}`) and prints
   exactly one `RESULT S11_dB_at_<f>=<x> f_res_GHz=<y>` line.

The lumped port must be port #1 with reference impedance 50 ohm.

## Judge gates (all must pass — exit 0 only then)

| # | gate | numeric rule |
|---|------|--------------|
| G1 | artifact sanity | py_compile OK; all 8 params present as numeric literals; `simulate` defined |
| G2 | physical sanity | er ∈ [3.5, 5.0]; sub_h ∈ [0.5, 2.5] mm; patch_L ∈ [20, 45] mm; patch_W ∈ [20, 55] mm; feed_inset ∈ (0, 0.45·patch_L]; mesh_res ∈ [0.4, 2.0] mm |
| G3 | sim runs | artifact exits 0 under a 9-min wall limit; RESULT line present; `antenna_results.json` covers 2.2–2.7 GHz with ≥ 21 points; raw `port_ut_1`/`port_it_1` exist |
| G4 | S11 at target | `S11_dB_at_target ≤ −10 dB` at 2.45 GHz |
| G5 | resonance | `f_res_GHz` (min \|S11\| in band) within ±2 % of 2.45 GHz |
| G6 | raw cross-check | judge re-computes S11(f) from the raw `port_ut_1`/`port_it_1` time series itself; max \|S11_judge − S11_artifact\| ≤ 1.5 dB over the band |
| G7 | **analytic oracle** | independent judge sim: openEMS effective permittivity of a ~50 Ω microstrip on 1.6 mm FR-4 vs Hammerstad-Jensen closed form, `|eeff_sim − eeff_HJ| / eeff_HJ ≤ 4 %` |
| G8 | convergence | judge imports the artifact and re-runs `simulate()` at `mesh_res×0.75`; spec must still hold at the finer mesh (S11 ≤ −10 dB and f_res shift ≤ 1.5 %) |
| G9 | judge integrity | sha256 of `judge/` tree identical before and after the run |

G8 note: the *depth* of an S11 dip is notoriously mesh-sensitive (a deep null
can move by 10+ dB between meshes while the spec still holds), so convergence
is defined as **the spec still holding under refinement**, not as a small
ΔS11. This is the honest convergence criterion; it is why the gate re-checks
G4+G5 on the refined mesh.

## Acceptance oracle

- **Hammerstad-Jensen closed form** for a ~50 Ω microstrip (W/h = 1.925,
  er = 4.4, h = 1.6 mm): `eeff_HJ = 3.33`. The judge simulates a straight
  line, extracts β from the phase slope of five field probes, derives
  `eeff_sim` and compares (gate G7, ≤ 4 %). Measured residual is ~3 % — the
  quasi-static formula itself is approximate; the 4 % bound is honest and
  documented, not fitted.
- **Patch quasi-static resonance** `c/(2(L+ΔL)√εeff)` is reported beside the
  measured `f_res` (informational; the feed-probe inductance and finite
  ground shift the real resonance by a few %).
- **Self-test**: 7 scripted single-edit mutants (wrong er, wrong patch
  length, deleted ground plane, feed at voltage null, mesh out of range,
  NaN er, substrate too thick) must each fail ≥ 1 gate; kill rate ≥ 90 %.

## Provenance

openEMS is GPL-2.0+ (github.com/thliebig/openEMS; Debian package
`python3-openems 0.0.35+git20190103.6a75e98+dfsg.1-3.2`, bookworm). The
geometry equations are textbook (Balanis; Pozar; Hammerstad-Jensen). The
artifact, judge and oracle are written from scratch for this demo; nothing
third-party is imported beyond the pinned tools.
