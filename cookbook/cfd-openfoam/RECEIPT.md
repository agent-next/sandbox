# RECEIPT — cfd-openfoam

Run inside a disposable Debian 12 (bookworm) sandbox, 2 vCPU, ~4 GB RAM,
2026-10-14.  Tool versions: `openfoam`/`libopenfoam` 1912.200626-1+b1,
`openfoam-examples` 1912.200626-1 (Debian bookworm, sha256-verified).

## `bash judge/setup.sh` — exit 0, ~16–23 s

*Fresh run from independent reproduction (see REPRODUCE.md):*

```
$ cd /home/user/w/cookbook/cfd-openfoam && time bash judge/setup.sh
[setup] installed OpenFOAM does not match the pins; reinstalling
[setup] Fetching apt package lists...
[setup] Downloading pinned packages (1912.200626-1+b1 + dependencies)...
[setup] sha256 OK: 23 packages match judge/package-sha256.txt
[setup] Installing (23 packages)...
sudo: unable to resolve host instance: Name or service not known
debconf: delaying package configuration, since apt-utils is not installed
[setup] OpenFOAM 1912.200626-1+b1 installed and verified
[setup] (versions recorded in judge/VERSIONS.txt; run `bash judge/versions.sh --check`)

real    0m22.453s
EXIT=0
```

*Note: this image already contained a partial/mismatched OpenFOAM state, so
setup took the "does not match the pins; reinstalling" branch — the pin
verification worked as designed. `bash judge/versions.sh --check` after
setup prints `judge/VERSIONS.txt is current`; dpkg reports
`openfoam=libopenfoam=1912.200626-1+b1`, `openfoam-examples=1912.200626-1`.*

## `bash judge/selftest.sh` — exit 0, 54–73 s, kill rate 100 %

*Fresh run from independent reproduction (see REPRODUCE.md):*

```
$ time bash judge/selftest.sh
[selftest] Regenerating mutant cases...
Created 10 mutants in /home/user/w/cookbook/cfd-openfoam/examples/bad

[selftest] Known-good cases (must PASS):
[selftest]   good/poiseuille  PASS  (7s)
[selftest]   good/cavity  PASS  (7s)

[selftest] Determinism check (same seed twice, verdict JSON except 'timing'):
[selftest]   good/poiseuille  deterministic (identical)
[selftest]   good/cavity  deterministic (identical)

[selftest] Known-bad mutants (must FAIL):
[selftest]   poiseuille_wrong_bc  killed (failed gates: 3,4)
[selftest]   poiseuille_wrong_viscosity  killed (failed gates: 3)
[selftest]   poiseuille_coarse_mesh  killed (failed gates: 2,3)
[selftest]   poiseuille_unconverged  killed (failed gates: 2,3,4)
[selftest]   poiseuille_wrong_outlet  killed (failed gates: 2,3,4)
[selftest]   cavity_wrong_lid  killed (failed gates: 5)
[selftest]   cavity_wrong_viscosity  killed (failed gates: 5)
[selftest]   cavity_coarse_mesh  killed (failed gates: 5)
[selftest]   cavity_unconverged  killed (failed gates: 2,5)
[selftest]   cavity_slip_wall  killed (failed gates: 5)

[selftest] ============================================
[selftest] good cases passed : 2/2
[selftest] determinism       : 2/2 identical
[selftest] mutants killed    : 10/10 (100%)
[selftest] ============================================
[selftest] SUCCESS

real    1m13.114s
EXIT=0
```

*Measured wall-time range across fresh runs: 54–73 s. Per-mutant failed-gate
lists are identical to the original RECEIPT (e.g. `poiseuille_wrong_outlet`
-> gates 2,3,4; `cavity_unconverged` -> 2,5).*

## `bash judge/grade.sh examples/good/poiseuille --json /tmp/v.json` — exit 0, ~6 s

```json
{
  "case_type": "poiseuille",
  "all_gates_passed": true,
  "gates": [
    {"gate": 1, "name": "Mesh quality", "passed": true,
     "details": {"checkMesh_exit": 0, "max_non_orthogonality": 0.0,
                 "max_skewness": 1.77636e-14, "cells": [20, 20, 1]}},
    {"gate": 2, "name": "Solver convergence", "passed": true,
     "details": {"icoFoam_exit": 0,
                 "final_initial_residuals": {"Ux": 1.85999e-14,
                     "Uy": 3.55576e-12, "p": 7.78605e-07},
                 "global_continuity_error": 2.06287e-11}},
    {"gate": 3, "name": "Poiseuille accuracy", "passed": true,
     "details": {"Re_measured": 99.6646, "nu": 0.005, "Umax": 0.996646,
                 "l2_error": 0.004253372684648054, "l2_tol": 0.02,
                 "dpdx_measured": -0.0392433435229767,
                 "dpdx_analytic": -0.04,
                 "dpdx_rel_err": 0.018916411925582605, "dpdx_tol": 0.15}},
    {"gate": 4, "name": "Poiseuille mesh convergence", "passed": true,
     "details": {"l2_errors": {"10": 0.018912535523490266,
                              "20": 0.004253372684648054,
                              "40": 0.0011340218991012952},
                 "orders": [2.152663616308129, 1.9071587704049107],
                 "avg_order": 2.02991119335652, "order_tol": 1.5}}
  ]
}
```

`[grade] exit code: 0 (0 = all gates passed)` — `real 0m5.894s`

## `bash judge/grade.sh examples/good/cavity --json /tmp/v.json` — exit 0, ~6 s

```json
{
  "case_type": "cavity",
  "all_gates_passed": true,
  "gates": [
    {"gate": 1, "name": "Mesh quality", "passed": true,
     "details": {"checkMesh_exit": 0, "max_non_orthogonality": 0.0,
                 "cells": [40, 40, 1]}},
    {"gate": 2, "name": "Solver convergence", "passed": true,
     "details": {"icoFoam_exit": 0,
                 "final_initial_residuals": {"Ux": 3.15e-09,
                     "Uy": 4.20e-09, "p": 1.07e-06},
                 "global_continuity_error": 2.8e-20}},
    {"gate": 5, "name": "Cavity vs Ghia et al. 1982", "passed": true,
     "details": {"Re_measured": 100.0, "nu": 0.01, "lid_velocity": 1.0,
                 "max_u_error": 0.0032611795690342393,
                 "max_v_error": 0.007316203511572167, "tol": 0.02,
                 "reference": "Ghia, U., Ghia, K.N., Shin, C.T. (1982).
                     J. Comput. Phys. 48(3), 387-411. Tables I & II, Re=100."}}
  ]
}
```

`[grade] exit code: 0 (0 = all gates passed)` — `real 0m6.200s`

## Key numbers

| metric | value | threshold |
|---|---|---|
| Poiseuille L2 profile error (20x20) | 0.00425 | <= 0.02 |
| Poiseuille mesh order | 2.15, 1.91 | >= 1.5 |
| Poiseuille dp/dx rel. err | 0.019 | <= 0.15 |
| Cavity max u err vs Ghia | 0.0033 | <= 0.02 |
| Cavity max v err vs Ghia | 0.0073 | <= 0.02 |
| Mutant kill rate | 10/10 (100 %) | >= 90 % |

## Hardening (2026-10-14, against cookbook/DEMO-STANDARD.md)

Standard sections addressed: **Reproducibility** and **Judge rules**.

### Criterion 1 — pinned tools, sha256-checked downloads

- `judge/package-sha256.txt` pins the exact version **and** sha256 of all
  23 .deb packages (openfoam, libopenfoam, openfoam-examples + the full
  transitive dependency closure) that `setup.sh` downloads. A Debian point
  release (binNMU) that rebuilds any of them changes a digest and
  `setup.sh` exits 1 instead of silently installing a different solver.
  The digest table is reproduced in `judge/VERSIONS.txt`.
- `judge/setup.sh` verifies every downloaded .deb before install
  (`sha256 OK: 23 packages match judge/package-sha256.txt` — output in the
  setup section above, re-verified in both fresh runs below).
- `judge/VERSIONS.txt` records the tools' own `-version` banners, the
  dpkg versions of everything installed, the digest table and the host
  toolchain; `bash judge/versions.sh --check` confirms it is current:

  ```
  $ bash judge/versions.sh --check
  versions.sh --check: verifying judge/VERSIONS.txt is current
  versions.sh: judge/VERSIONS.txt is current
  ```

- `judge/requirements.txt` (matplotlib/numpy, used only by media)
  pins exact versions **with pip hashes** and installs with
  `pip install --require-hashes -r judge/requirements.txt`:

  ```
  Successfully installed contourpy-1.3.1 cycler-0.12.1 fonttools-4.55.3
  kiwisolver-1.4.8 matplotlib-3.8.4 numpy-2.0.2 packaging-25.0 pillow-11.1.0
  pyparsing-3.2.3 python-dateutil-2.9.0 six-1.17.0
  ```

- Idempotency: a second `setup.sh` right after the first prints
  `[setup] OpenFOAM 1912.200626-1+b1 already installed` and exits 0.

### Criterion 2 — determinism, checked by selftest

`selftest.sh` re-runs each good case at the same seed and diffs the two
verdict JSONs after removing the `timing` key (the only field allowed to
vary). It now **fails** on a determinism mismatch (verified by a negative
test: injecting a random field into the verdict made selftest exit 1 with
`FAIL: verdict JSON not deterministic at seed 42`; after reverting, it
exits 0 again):

```
[selftest] Determinism check (same seed twice, verdict JSON except 'timing'):
[selftest]   good/poiseuille  deterministic (identical)
[selftest]   good/cavity  deterministic (identical)
...
[selftest] determinism       : 2/2 identical
[selftest] SUCCESS
```

### Criterion 3 — two fresh-setup runs, side by side

Run A = `rm -rf`-equivalent from nothing (fresh sandbox state: no
`~/.openfoam_version`, no `~/.openfoam_installed`, no openfoam packages).
Run B = every package setup.sh had installed **purged** (`dpkg --purge`
openfoam, libopenfoam, openfoam-examples and all 20 dependency packages),
then setup/selftest/grade again. Verdict JSONs from the two runs are
byte-identical modulo `timing`/`seed` (checked programmatically:
`run1==run2 (excl timing/seed): True` for both cases).

| step | Run A | Run B |
|---|---|---|
| `setup.sh` | exit 0, 19 s | exit 0, 17 s |
| `selftest.sh` | exit 0, 63 s, 2/2 good, 10/10 killed | exit 0, 63 s, 2/2 good, 10/10 killed |
| `grade.sh good/poiseuille --seed 42` | exit 0, 6 s | exit 0, 5 s |
| `grade.sh good/cavity --seed 42` | exit 0, 6 s | exit 0, 6 s |

Key numbers — identical across runs:

| metric | Run A | Run B | threshold |
|---|---|---|---|
| Poiseuille L2 profile error | 0.004253 | 0.004253 | <= 0.02 |
| Poiseuille dp/dx rel. err | 0.018916 | 0.018916 | <= 0.15 |
| Poiseuille Re measured | 99.6646 | 99.6646 | 100 ± 10 % |
| Mesh-convergence orders | 2.153, 1.907 | 2.153, 1.907 | >= 1.5 |
| Cavity max u err vs Ghia | 0.003261 | 0.003261 | <= 0.02 |
| Cavity max v err vs Ghia | 0.007316 | 0.007316 | <= 0.02 |

### Criterion 4 — judge strength

- 10 scripted single-edit mutants (`judge/mutants.py`), all killed in both
  fresh runs: **kill rate 10/10 = 100 % >= 90 %** (full list in the
  selftest section above).
- Every gate compares against an independent oracle (see the "Acceptance
  oracle" section of SPEC.md): Gate 3 — closed-form Poiseuille parabola +
  analytic pressure gradient + Re consistency; Gate 4 — measured
  convergence order under refinement of the artifact's own mesh/inlet;
  Gate 5 — published Ghia, Ghia & Shin (1982) tabulated centreline data.
  Gates 1–2 verify the judge's own run of the toolchain against numeric
  quality/residual thresholds, not merely that the tools exited 0.

### Criterion 5 — lead findings

1. **Pin by exact package versions + .deb sha256** — done: the 23-digest
   table in `judge/package-sha256.txt` (mirrored into
   `judge/VERSIONS.txt`), enforced by `setup.sh` before install. Evidence:
   criterion 1 above. OpenFOAM 1912 from Debian is kept as the lead
   allowed since it reproduces bit-stably across fresh runs (criterion 3).
2. **Record the lead's end-to-end run in RECEIPT** — the lead ran
   `run.py` end to end: **EXIT 0, 90 s wall, 10/10 mutants killed,
   Poiseuille L2 0.43 % (0.0042534), Ghia max u/v error
   0.0033/0.0073, sandbox confirmed deleted via `sbx list`**. Numbers match
   the local runs in criteria 2-3 exactly (same seed).
3. **Media plan recorded** — velocity-profile vs analytic Poiseuille curve
   with the 2 % band; cavity centreline u/v vs Ghia points; mesh
   convergence log-log plot with fitted order; cavity-flow video from
   saved time directories. Shipped in part 2 (`media/`).

### Deviations (hardening)

- The "two fresh sandboxes" of the standard were emulated on one machine
  by purging every package `setup.sh` installs and deleting its state
  files between runs — the next best thing without burning two cloud
  sandboxes; package state after the purge was verified empty first.
- `run.py` was not re-run end to end by this agent (no `SBX_API_KEY` in
  this environment); the lead's run above stands as the end-to-end
  evidence, and `python3 -m py_compile run.py` passes.
- `selftest.sh` previously counted a determinism failure without failing
  on it — fixed in this pass (criterion 2, with negative test).

## run.py verification

`python3 -m py_compile run.py` passes. The in-sandbox command sequence it
sends to `sbx exec` was verified directly in this sandbox — the same
`bash -c 'cd repo/cookbook/cfd-openfoam && bash judge/…'` steps shown
above (clone step verified against the public remote
`https://github.com/agent-next/sandbox.git`). The end-to-end cloud run is
left to the maintainer.

## Deviations

- Setup install wall time (~16 s) reflects a warm Debian mirror; a cold
  sandbox may take a few minutes for ~600 MB of dependencies.
- The Ghia tolerance is 0.02 (lid-speed units): the 40x40 good case sits
  at 0.0033/0.0073 max error while a 10x10 mesh is at ~0.04, so the gate
  separates correct from too-coarse with ~2x margin on both sides.
- Gate 4 resamples the artifact's own inlet profile onto each refinement
  level (the earlier draft overwrote it with the analytic parabola, which
  would have graded the judge's input, not the artifact's).
