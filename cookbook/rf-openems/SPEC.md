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
   S11 sweep over 2.2–2.7 GHz: **strictly increasing frequencies, covering
   the full band, with at least 51 points** (the judge resamples this
   sweep onto its own 51-point grid, so a sparse or reordered grid is
   rejected outright — see G3).
3. When run as `__main__`, it calls `simulate()` with the parameter block,
   writes `antenna_results.json` in the current directory
   (`{"S11_dB_at_target", "f_res_GHz", "freqs_GHz", "S11_dB"}`) and prints
   exactly one `RESULT S11_dB_at_<f>=<x> f_res_GHz=<y>` line.

The lumped port must be port #1 with reference impedance 50 ohm.

## Judge gates (all must pass — exit 0 only then)

| # | gate | numeric rule |
|---|------|--------------|
| G1 | artifact sanity | source compiles; all 8 params present as numeric literals; `simulate` defined |
| G2 | physical sanity | er ∈ [3.5, 5.0]; sub_h ∈ [0.5, 2.5] mm; patch_L ∈ [20, 45] mm; patch_W ∈ [20, 55] mm; feed_inset ∈ (0, 0.45·patch_L]; mesh_res ∈ [0.4, 2.0] mm |
| G3 | sim runs | artifact exits 0 under a 9-min wall limit; RESULT line present; `antenna_results.json` carries a **valid sweep grid** (strictly increasing, covering 2.2–2.7 GHz, ≥ 51 points — reordered or gappy sweeps are rejected with a `sweep_grid:` detail, coarse and fine path alike); raw `port_ut_1`/`port_it_1` exist, **were written inside a recorded solver-run window, and still match the size+sha256 the judge's runner hashed at that Run's end** (the journal lives on an unlinked file descriptor the artifact cannot see; a child that burns < 5 CPU-s doesn't count either); reported `S11_dB_at_target`/`f_res_GHz` must agree with the judge-derived curve (≤ 1.5 dB / ≤ 0.025 GHz) |
| G4 | S11 at target | `S11(2.45 GHz) ≤ −10 dB`, **computed by the judge** — the DFT of the raw port time series evaluated at exactly 2.45 GHz, never interpolated on the artifact's own grid |
| G5 | resonance | judge-derived resonance (min \|S11\| on the judge's own 51-point 2.2–2.7 GHz grid) within ±2 % of 2.45 GHz |
| G6 | raw cross-check | judge re-computes S11(f) from the raw `port_ut_1`/`port_it_1` time series itself on the judge grid and compares against the artifact's sweep resampled onto that grid; max \|S11_judge − S11_artifact\| ≤ 1.5 dB over the band |
| G7 | **analytic oracle** | independent judge sim: openEMS effective permittivity of a ~50 Ω microstrip on 1.6 mm FR-4 vs Hammerstad-Jensen closed form, `|eeff_sim − eeff_HJ| / eeff_HJ ≤ 4 %` |
| G8 | convergence | judge re-runs the artifact's `simulate()` in-process-isolated at `mesh_res×0.75` under the same provenance journal; the fine-mesh report must pass the same sweep-grid validation, the fine-mesh raw port files are re-derived by the judge on the judge grid and **G4 and G5 are rechecked on them** (S11 ≤ −10 dB at 2.45 GHz AND f_res within ±2 % of 2.45 GHz) plus f_res shift ≤ 1.5 % vs the coarse result |
| G9 | judge integrity | sha256 of `judge/` tree — **including any `__pycache__`/`.pyc`** — identical before and after the run, and the judge's private module copy untouched |

G8 note: the *depth* of an S11 dip is notoriously mesh-sensitive (a deep null
can move by 10+ dB between meshes while the spec still holds), so convergence
is defined as **the spec still holding under refinement**, not as a small
ΔS11. This is the honest convergence criterion; it is why the gate re-checks
G4+G5 on the refined mesh — a coarse resonance barely inside the ±2 % band
cannot pass if refinement pushes it out.

## Judge hardening (what the gates assume)

- **Every reported number is re-derived or re-checked.** G4/G5/G6/G8 all
  act on S11 the judge computed itself from raw port time series; the
  artifact's own scalars are only a report, cross-checked in G3.
- **Acceptance values live on a judge-owned frequency grid.** The judge
  derives S11 on its own 51-point 2.2–2.7 GHz grid (2.45 GHz is a node),
  not on whatever grid the artifact reports; the artifact's sweep is only
  an input that must be strictly increasing, cover the band and carry at
  least 51 points, and is then resampled for G6. A reordered sweep (the
  classic `np.interp` clamping trick: move a deep sample to the end and
  every query at or beyond it reads that sample) or a single-frequency
  report is rejected with an explicit `sweep_grid` detail on both the
  coarse and the fine path (`judge/test_grid.py` pins this down).
- **Provenance, not presence — and content, not timestamps.** The judge's
  runner wraps `FDTD.Run` and, at each Run's end, journals the window
  plus the **size and sha256 of both raw port files** into a journal that
  lives on an unlinked file descriptor: the judge creates the file,
  unlinks it, and hands the child only the open fd. The artifact cannot
  discover the journal from argv/env/cwd, cannot forge an `ok:true` line
  by writing `fdtd_runs.jsonl` in its workdir (the pre-hardening journal
  location — `bad_forge_journal.py` does exactly this and dies), and any
  replacement of the port files after Run returns fails the sha256
  comparison regardless of timestamps (`bad_late_ports_swap.py` rewrites
  the files 10 s after Run — inside the old 30 s slack, physics unchanged
  — and dies). A child that burns < 5 CPU-s does not count as a solve
  either.
- **Executable inputs are protected, not just sources.** Before importing
  any helper the judge copies `judge/*.py` into a private directory,
  imports only from there, and runs with `-B`/`PYTHONDONTWRITEBYTECODE`,
  so a `__pycache__` forged to match source mtimes is never executed —
  and G9's tree hash would catch the plant anyway. The private copy is
  re-hashed before the lazily-imported oracle module loads.
- **`--skip-convergence` is a partial grade**: G8 is recorded
  `not run`, `all_pass` is false, and grade.sh exits 2 when nothing else
  failed (1 on a real failure, 0 only when every gate passed). A gate
  recorded `not run` is a skip, never a kill: selftest only counts a
  mutant as killed when its targeted gate *ran and failed*, so
  `--skip-convergence` can never "kill" the G8 mutants by skipping them.

## Threat model

What the provenance hardening does and does not defend against. The
artifact's code runs in the same interpreter as the judge's runner hook
(and as the same OS user as the judge itself), so:

- **Defended (this hardening):** forging the journal by writing
  `fdtd_runs.jsonl` in the workdir or any guessable/discoverable path —
  the journal is an unlinked fd, and argv/env/cwd disclose nothing;
  replacing port files after `Run` returns — sha256 pinned at Run end
  decides, so the 30 s mtime slack can no longer be ridden
  (`bad_late_ports_swap`); replaying cached/fabricated port files without
  a solver run (`bad_replay_cached`, `bad_forge_journal`); steering
  interpolated acceptance values with a reordered or gappy sweep
  (`bad_shuffled_grid`).
- **Residual, in-process:** the runner hook (a `_JFDTD` subclass) lives
  in the child's `__main__`; artifact code in that same interpreter can
  in principle find the journal fd by walking `/proc/self/fd` (the fd
  survives, pointing at an unlinked inode, and is writable via
  `os.write`) or by introspecting the hook object via `gc`, then append
  entries whose port hashes match its fabricated files, while burning
  CPU. Nothing named by a path is secret from a same-UID process. This is
  defence in depth, not a security boundary — as before, the disposable
  sandbox (separate machine, torn down after the run) is the actual
  isolation boundary, and G9's tree hash plus the private module copy
  cover the judge's own executable inputs.

## Exit codes

| rc | meaning |
|----|---------|
| 0 | every gate passed |
| 1 | at least one gate failed |
| 2 | partial grade — `--skip-convergence` left G8 unrun, no other failure |

`--timeout` (default 540 s = the G3 9-min limit) bounds the artifact's own
run; `--conv-timeout` (default 1200 s) bounds the judge's fine-mesh re-run,
which the artifact contract does not cover and which needs ~2x the cells.

**Verdict determinism:** this openEMS build is not bit-deterministic — the
same sim stops its energy-decay loop a few timesteps apart and measured
floats wander at ~1e-4 relative (~0.1 dB on S11, ~4e-3 deg on probe phase).
Gate *decisions* use the raw values and our margins are far above the noise;
for the *recorded* verdict, every sim-derived number is reported on a
stated grid (S11-type values: 1 dB; GHz/eeff: 0.01; percents: 0.1; probe
phases: 1 deg) so two same-seed verdicts are byte-identical outside the
`timing` block (checked by selftest.sh).

## Acceptance oracle

- **Hammerstad-Jensen closed form** for a ~50 Ω microstrip (W/h = 1.925,
  er = 4.4, h = 1.6 mm): `eeff_HJ = 3.33`. The judge simulates a straight
  line, extracts β from the phase slope of five field probes, derives
  `eeff_sim` and compares (gate G7, ≤ 4 %). Measured residual is 2.8 % — the
  quasi-static formula itself is approximate; the 4 % bound is honest and
  documented, not fitted.
- **Patch quasi-static resonance** `c/(2(L+ΔL)√εeff)` is reported beside the
  measured `f_res` (informational; the feed-probe inductance and finite
  ground shift the real resonance by a few %).
- **Self-test**: 18 scripted single-edit mutants — wrong er, wrong patch
  length, deleted ground plane, feed at voltage null, mesh out of range,
  NaN er, substrate too thick, fabricated results only, scalar lies over a
  real sim, fabricated raw port files, a reordered sweep grid, port files
  swapped after Run, a forged `ok:true` journal line, doctored sweep,
  mid-run tampering with the judge's module copy, a different geometry at
  the fine mesh, a canned fine-mesh result, a forged `.pyc` — must each
  fail **its own targeted gate** (a gate recorded "not run" is a skip,
  not a kill); kill rate 100 %, and a crash or unparseable verdict is
  a self-test failure, not a kill. The sweep-grid validation itself has
  solver-free unit tests (`judge/test_grid.py`) that selftest runs first.

## Provenance

openEMS is GPL-2.0+ (github.com/thliebig/openEMS; Debian package
`python3-openems 0.0.35+git20190103.6a75e98+dfsg.1-3.2`, bookworm). The
geometry equations are textbook (Balanis; Pozar; Hammerstad-Jensen). The
artifact, judge and oracle are written from scratch for this demo; nothing
third-party is imported beyond the pinned tools.
