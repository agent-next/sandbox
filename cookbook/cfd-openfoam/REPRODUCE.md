VERDICT: REPRODUCED

# REPRODUCE — cfd-openfoam

Independent reproduction of `cookbook/cfd-openfoam/` from `README.md` +
`SPEC.md` only, in a fresh sandbox. RECEIPT.md was read only after all
numbers below were collected. Reproducer, not builder: no demo files were
modified.

## Environment

- Debian GNU/Linux 12 (bookworm), 2 vCPU, ~3.8 GB RAM — same shape as the
  RECEIPT environment (already inside a disposable sandbox, so the
  README's "create a CPU sandbox" step was satisfied by the environment;
  `SBX_API_KEY`/`sbx` are absent here, see "README issues" #1).
- `python3 3.12.15`, `ffmpeg 5.1.9-0+deb12u1`, passwordless `sudo`.
- Repo `agent-next/sandbox` checked out at `1a25b2e`, clean tree.

## Step 1 — `bash judge/setup.sh` (README: install pinned OpenFOAM)

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

Note: this image already contained a partial/mismatched OpenFOAM state, so
setup took the "does not match the pins; reinstalling" branch — the pin
verification worked as designed. `bash judge/versions.sh --check` after
setup prints `judge/VERSIONS.txt is current`; dpkg reports
`openfoam=libopenfoam=1912.200626-1+b1`, `openfoam-examples=1912.200626-1`.

## Step 2 — `bash judge/selftest.sh` (README: prove the judge can fail)

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

Per-mutant failed-gate lists are identical to RECEIPT's (e.g.
`poiseuille_wrong_outlet` -> gates 2,3,4; `cavity_unconverged` -> 2,5).

## Step 3 — grade the good cases (seed 42, as the RECEIPT used)

```
$ time bash judge/grade.sh examples/good/poiseuille --json /tmp/repro/verdict_poiseuille.json --seed 42
...
[grade] exit code: 0 (0 = all gates passed)
real    0m6.480s   EXIT=0

$ time bash judge/grade.sh examples/good/cavity --json /tmp/repro/verdict_cavity.json --seed 42
...
[grade] exit code: 0 (0 = all gates passed)
real    0m6.883s   EXIT=0
```

My poiseuille verdict JSON, verbatim:

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
               "global_continuity_error": 2.06287e-11,
               "residuals_ok": true, "continuity_ok": true}},
  {"gate": 3, "name": "Poiseuille accuracy", "passed": true,
   "details": {"Re_measured": 99.66460000000001, "Re_target": 100.0,
               "nu": 0.005, "Umax": 0.996646,
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
 ],
 "seed": 42,
 "timing": {"wall_seconds": 6.331}
}
```

My cavity verdict (key details; per-station `u_errors`/`v_errors` elided):

```json
{
 "case_type": "cavity",
 "all_gates_passed": true,
 "gates": [
  {"gate": 1, "name": "Mesh quality", "passed": true,
   "details": {"checkMesh_exit": 0, "max_non_orthogonality": 0.0,
               "max_skewness": 3.14018e-14, "cells": [40, 40, 1]}},
  {"gate": 2, "name": "Solver convergence", "passed": true,
   "details": {"icoFoam_exit": 0,
               "final_initial_residuals": {"Ux": 3.15359e-09,
                   "Uy": 4.19691e-09, "p": 1.07314e-06},
               "global_continuity_error": 2.80447e-20,
               "residuals_ok": true, "continuity_ok": true}},
  {"gate": 5, "name": "Cavity vs Ghia et al. 1982", "passed": true,
   "details": {"Re_measured": 100.0, "Re_target": 100.0, "nu": 0.01,
               "lid_velocity": 1.0,
               "max_u_error": 0.0032611795690342393,
               "max_v_error": 0.007316203511572167, "tol": 0.02,
               "reference": "Ghia, U., Ghia, K.N., Shin, C.T. (1982). ..."}}
 ],
 "seed": 42,
 "timing": {"wall_seconds": 6.774}
}
```

## Step 4 — determinism: `grade.sh` twice, same seed, diff ignoring `timing`

```
$ bash judge/grade.sh examples/good/poiseuille --json det_1.json --seed 42
$ bash judge/grade.sh examples/good/poiseuille --json det_2.json --seed 42
$ bash judge/grade.sh examples/good/cavity    --json det_1.json --seed 42   # separate files
$ bash judge/grade.sh examples/good/cavity    --json det_2.json --seed 42
```

JSON compare after `del v["timing"]`:

| case | identical (excl. timing) | wall run1 | wall run2 |
|---|---|---|---|
| poiseuille | **True** | 6.049 s | 5.996 s |
| cavity | **True** | 6.898 s | 6.590 s |

Byte-identical verdict JSONs apart from `timing` — matches RECEIPT
criterion 2 (`2/2 identical`) and the selftest's own determinism check.

## Step 5 — media rebuild vs `media/MANIFEST.json`

Prereqs: `ffmpeg` already at the pinned `5.1.9-0+deb12u1`; matplotlib
installed per `judge/requirements.txt`:

```
$ python3 -m venv /tmp/ofmedia && /tmp/ofmedia/bin/pip install \
    --require-hashes -r judge/requirements.txt
Successfully installed contourpy-1.3.1 cycler-0.12.1 fonttools-4.55.3
kiwisolver-1.4.8 matplotlib-3.8.4 numpy-2.0.2 packaging-25.0 pillow-11.1.0
pyparsing-3.2.3 python-dateutil-2.9.0 six-1.17.0
```

```
$ PYTHON=/tmp/ofmedia/bin/python bash media/make_media.sh
[media] matplotlib 3.8.4
[media] ffmpeg 5.1.9-0+deb12u1
=== 1. replay: known-bad -> partly fixed -> good (cavity) ===
Created 10 mutants in /home/user/w/cookbook/cfd-openfoam/examples/bad
=== 2. good poiseuille with trace ===
=== 3. all mutants (kill-rate bars) ===
=== 4. guard: every expected judge output present ===
=== 5. figures ===
wrote /home/user/w/cookbook/cfd-openfoam/media/result.png
wrote /home/user/w/cookbook/cfd-openfoam/media/loop.png
=== 6. video frames (lossless PNG) ===
wrote 60 frames to /tmp/of-frames.8wVSLQ
=== 7. lossless master (crf 0, gitignored) ===
=== 8. web encode (crf 18 preset slow, faststart) ===
=== 9. MANIFEST.json ===
  result.png    764886 bytes  a736acd7020617ea...
  loop.png      231095 bytes  1a728a44ab2f54a6...
  demo.mp4     1773182 bytes  a3b331bba78a8009...
make_media: done
EXIT=0
```

sha256 of rebuilt files vs the committed `media/MANIFEST.json`:

| file | manifest sha256 (first 16) | rebuilt sha256 (first 16) | bytes | match |
|---|---|---|---|---|
| result.png | a736acd7020617ea | a736acd7020617ea | 764886 | **MATCH** |
| loop.png | 1a728a44ab2f54a6 | 1a728a44ab2f54a6 | 231095 | **MATCH** |
| demo.mp4 | a3b331bba78a8009 | a3b331bba78a8009 | 1773182 | **MATCH** |

All three artifacts regenerate **bit-identically** (the rebuilt
MANIFEST.json also matches the committed one; `git status` on `media/`
stays clean). No PNG/MP4 divergence to explain — the underlying judge
outputs are deterministic at seed 42.

## Comparison with RECEIPT.md

SPEC tolerances in brackets. RECEIPT's cavity gate-2 residuals are printed
rounded; mine match at that precision and to full float precision
wherever the RECEIPT prints full precision.

| item | RECEIPT | this run | SPEC tol | verdict |
|---|---|---|---|---|
| setup.sh exit / wall | 0 / ~16 s | 0 / 22.5 s | n/a (README allows ~16 s–4 min) | match |
| setup sha256 check | 23 pkgs verified | 23 pkgs verified | n/a | match |
| selftest exit / wall | 0 / ~54 s | 0 / 73.1 s | n/a (RECEIPT fresh runs took 63 s) | match |
| selftest good cases | 2/2 PASS | 2/2 PASS | n/a | match |
| selftest determinism | 2/2 identical | 2/2 identical | n/a | match |
| mutant kill rate | 10/10 (100 %) | 10/10 (100 %) | [>= 90 %, >= 5 mutants] | match |
| per-mutant failed gates | (list) | identical list | n/a | match |
| poiseuille all_gates_passed | true | true | n/a | match |
| gate 1 max_skewness | 1.77636e-14 | 1.77636e-14 | [<= 4] | match |
| gate 2 residuals Ux/Uy/p | 1.85999e-14 / 3.55576e-12 / 7.78605e-07 | identical | [< 1e-5] | match |
| gate 2 continuity | 2.06287e-11 | 2.06287e-11 | [< 1e-8] | match |
| gate 3 Re_measured | 99.6646 | 99.66460000000001 | [|Re-100|/100 <= 0.10] | match |
| gate 3 L2 profile error | 0.004253372684648054 | identical | [<= 0.02] | match |
| gate 3 dpdx rel err | 0.018916411925582605 | identical | [<= 0.15] | match |
| gate 4 orders | 2.152663616308129, 1.9071587704049107 | identical | [>= 1.5] | match |
| gate 4 l2_errors 10/20/40 | 0.018912535523490266 / 0.004253372684648054 / 0.0011340218991012952 | identical | n/a | match |
| cavity all_gates_passed | true | true | n/a | match |
| cavity gate 2 residuals | ~3.15e-9 / 4.20e-9 / 1.07e-6 | 3.15359e-09 / 4.19691e-09 / 1.07314e-06 | [< 1e-5] | match |
| cavity gate 2 continuity | ~2.8e-20 | 2.80447e-20 | [< 1e-8] | match |
| gate 5 max_u_error vs Ghia | 0.0032611795690342393 | identical | [<= 0.02] | match |
| gate 5 max_v_error vs Ghia | 0.007316203511572167 | identical | [<= 0.02] | match |
| grade wall times | ~6 s each | 6.3–6.9 s | n/a | match |
| openfoam / libopenfoam | 1912.200626-1+b1 | 1912.200626-1+b1 | pinned | match |
| openfoam-examples | 1912.200626-1 | 1912.200626-1 | pinned | match |
| ffmpeg | 5.1.9-0+deb12u1 | 5.1.9-0+deb12u1 | pinned (VERSIONS.txt) | match |
| matplotlib | 3.8.4 | 3.8.4 | pinned (requirements.txt) | match |
| media sha256 x3 | MANIFEST values | bit-identical | n/a | match |

Every gate verdict, kill rate, key metric (to full printed float
precision), tool version and media hash matches. Zero mismatches.

## README issues found (unclear / wrong / missing)

1. **"Create a CPU sandbox" is not actionable from inside a sandbox
   without credentials.** `run.py` needs `SBX_API_KEY`/`E2B_API_KEY` and
   the `sbx` CLI; neither exists in this environment
   (`run.py` would exit `run.py: export SBX_API_KEY ... first`). The
   README never spells out the plain in-sandbox sequence
   (`setup.sh -> selftest.sh -> grade.sh`), which is what the demo
   actually reduces to once you are inside the sandbox. Worked around by
   running those steps directly — the environment already matched the
   spec (Debian 12, 2 vCPU).
2. **`setup.sh` needs root or passwordless sudo — undocumented.** It
   calls `apt-get`; in this sandbox `sudo -n` works (with a harmless
   `sudo: unable to resolve host instance` warning). A README user
   without sudo would fail silently until the apt step.
3. **`make_media.sh` matplotlib prerequisite is not in the README.** The
   README says media is regenerated by `media/make_media.sh` but not that
   it needs a venv; you only discover it by running the script, which
   prints the venv + `--require-hashes` command (documented in
   `judge/requirements.txt`). Following that hint worked.
4. **RECEIPT setup transcript is stale vs the current script.** It shows
   per-file `sha256 OK: <pkg>.deb` lines and apt `Setting up ...` output;
   the current `setup.sh` prints one aggregate line
   (`sha256 OK: 23 packages match judge/package-sha256.txt`) and sends
   apt output to /dev/null. RECEIPT's own criterion-1 section quotes the
   current line correctly — only the top transcript predates the script.
   Cosmetic.
5. **`grade.sh` usage string documents only `--json`**;
   `--seed`/`--trace` are accepted but hidden. The RECEIPT/replay uses
   `--seed 42` — a reproducer has to read the script to learn that flag
   (default seed 0 still produces identical verdicts, since the seed is
   only recorded in the JSON, not used by the judge).
6. **Selftest wall time exceeded the README table** (~54 s claimed vs
   73.1 s measured; RECEIPT's own fresh runs took 63 s). Not a failure —
   the table says "~" — but the README number looks optimistic on a
   cold-ish image.

## Cleanup

- All solver output lives in gitignored dirs (`examples/bad/`,
  `media/judge_runs/`, `media/master/`, `__pycache__/`); `git status`
  shows zero tracked modifications — including `judge/VERSIONS.txt`, which
  `setup.sh` regenerated byte-identically.
- Scratch outside the repo (`/tmp/repro`, `/tmp/ofmedia`, mktemp dirs)
  deleted after use. No sandboxes/snapshots/templates created by this
  run, so none deleted.
