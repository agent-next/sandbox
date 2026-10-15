# RECEIPT — physx-drop-test

Real command output from running the demo's judge steps, on 2 vCPU /
~4 GB RAM, Linux x86_64 (Debian, Python 3.12.15), headless CPU, no GPU.
Copy-paste, not paraphrase; wall times from `time` around each command.

Two from-nothing installs are compared. **Run A** was the first ever run in
this sandbox (no venv, no pip cache). Before **run C** the venv
(`$HOME/.venvs/physx-drop-test`), the warp kernel cache and pip's HTTP
cache (`~/.cache/pip`) were all deleted, so `judge/setup.sh` downloaded
and sha256-verified every wheel from PyPI again. Both grade runs produced
**byte-identical verdict JSON** (excluding `timing`).

## Run A (first run in a fresh sandbox)

### `bash judge/setup.sh` — exit 0, 2 m 22 s

The pip download lines of run A were not retained in full (output was
piped through `tail`); the lines below are the verbatim tail that was
captured. The complete pip output of a from-nothing install is pasted
under run C.

```
$ time bash judge/setup.sh
[setup] creating venv at /home/user/.venvs/physx-drop-test
[setup] installing pinned wheels (sha256-verified via --require-hashes)
Collecting newton-usd-schemas==0.5.0 (from -r .../judge/requirements.txt (line 15))
  Downloading newton_usd_schemas-0.5.0-py3-none-any.whl (22 kB)
Collecting warp-lang==1.17.0 (from -r .../judge/requirements.txt (line 17))
  Downloading warp_lang-1.17.0-py3-none-manylinux_2_28_x86_64.whl (164.3 MB)
     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 164.3/164.3 MB 19.5 MB/s eta 0:00:00
Collecting numpy==2.2.6 (from -r .../judge/requirements.txt (line 19))
  Downloading numpy-2.2.6-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl (16.5 MB)
     ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 16.5/16.5 MB 69.7 MB/s eta 0:00:00
Collecting packaging==23.2 (from -r .../judge/requirements.txt (line 24))
  Downloading packaging-23.2-py3-none-any.whl (53 kB)
Installing collected packages: packaging, ovstage, numpy, newton-usd-schemas, warp-lang, ovphysx
Successfully installed newton-usd-schemas-0.5.0 numpy-2.2.6 ovphysx-0.6.3 ovstage-0.2.0.377349 packaging-23.2 warp-lang-1.17.0

[notice] A new release of pip is available: 25.0.1 -> 26.2.1
[notice] To run: python3 -m pip install --upgrade pip
[setup] ovphysx native library loads: True
[setup] installed versions:
newton-usd-schemas==0.5.0
numpy==2.2.6
ovphysx==0.6.3
ovstage==0.2.0.377349
packaging==23.2
warp-lang==1.17.0
[setup] python: Python 3.12.15
[setup] done.

real	2m21.970s
user	0m34.996s
sys	0m20.815s
```

### `bash judge/selftest.sh` — exit 0, 3 m 04 s

```
$ time bash judge/selftest.sh
[selftest] 1/4 known-good scene must pass
[selftest]   ok (all gates passed)
[selftest] 2/4 known-bad mutants must each fail
[mutants] wrote 7 single-edit mutants to /tmp/physx-selftest.vBnuvd/mutants
[selftest]   killed:   cm-units  (failed: G4_resting)
[selftest]   killed:   gravity-flip  (failed: G2_freefall, G3_contact_time, G4_resting, G6_energy, G5_bounce_apex)
[selftest]   killed:   mass-zero  (failed: G1_loads)
[selftest]   killed:   no-ground-collision  (failed: G2_freefall, G3_contact_time, G4_resting, G5_bounce_apex)
[selftest]   killed:   no-rigidbody  (failed: G2_freefall, G3_contact_time, G4_resting)
[selftest]   killed:   restitution-over-unity  (failed: G3_contact_time, G5_bounce_apex)
[selftest]   killed:   spawn-inside-ground  (failed: G2_freefall, G3_contact_time, G6_energy)
[selftest] 3/4 kill rate: 7/7 = 100%
[selftest] 4/4 determinism (same seed, byte-identical JSON excl timing)
  identical
[selftest] PASS: judge kills 7/7 mutants, good passes, deterministic

real	3m3.760s
user	1m10.196s
sys	0m29.695s
```

### `bash judge/grade.sh examples/good/scene.usda --json /tmp/v.json` — exit 0, 22 s

```
$ time bash judge/grade.sh examples/good/scene.usda --json /tmp/v.json
[grade] exit code: 0 (0 = all gates passed)

real	0m21.947s
user	0m6.566s
sys	0m3.256s
```

`/tmp/v.json` (complete, `seed: 0`, `timing.wall_seconds: 21.269`; a
`grade.sh` invocation from outside the demo dir was first rejected with
`[grade] ERROR: no such file: examples/good/scene.usda`, exit 2 — paths
are relative to the invocation directory):

```json
{
  "gates": {
    "G1_loads":       { "passed": true },
    "G2_freefall":    { "passed": true },
    "G3_contact_time": { "passed": true },
    "G4_resting":     { "passed": true },
    "G6_energy":      { "passed": true },
    "G5_bounce_apex": { "passed": true, "detail": {
        "apex_analytic_m": 0.375, "apex_sim_m": 0.3733, "rel_error": 0.0043 } }
  },
  "all_gates_passed": true,
  "bodies": {
    "Box": {
      "G1_loads":       { "passed": true, "detail": { "steps_sampled": 2400, "mass_kg": 4.0, "mass_expected_kg": 4.0 } },
      "G2_freefall":    { "passed": true, "detail": { "g_fit": 9.81, "max_rel_residual": 0.0, "max_abs_residual_m": 0.0, "fit_start_s": 0.0, "fit_end_s": 0.3708, "y0_m": 0.7998, "y0_expected_m": 0.8 } },
      "G3_contact_time": { "passed": true, "detail": { "t_contact_analytic_s": 0.37773, "t_contact_sim_s": 0.375, "delta_frames": 0.65 } },
      "G4_resting":     { "passed": true, "detail": { "y_final_m": 0.1, "y_rest_m": 0.1, "error_mm": 0.0 } },
      "G6_energy":      { "passed": true, "detail": { "E0_J": 31.3853, "E_final_J": 3.924, "max_step_gain_J": 0.02142, "max_step_gain_allowed_J": 0.15693 } }
    },
    "Ball": {
      "G1_loads":       { "passed": true, "detail": { "steps_sampled": 2400, "mass_kg": 1.0, "mass_expected_kg": 1.0 } },
      "G2_freefall":    { "passed": true, "detail": { "g_fit": 9.81, "max_rel_residual": 0.0, "max_abs_residual_m": 0.0, "fit_start_s": 0.0, "fit_end_s": 0.4667, "y0_m": 1.1998, "y0_expected_m": 1.2 } },
      "G3_contact_time": { "passed": true, "detail": { "t_contact_analytic_s": 0.47353, "t_contact_sim_s": 0.47083, "delta_frames": 0.65 } },
      "G4_resting":     { "passed": true, "detail": { "y_final_m": 0.1, "y_rest_m": 0.1, "error_mm": 0.0 } },
      "G5_bounce_apex": { "passed": true, "detail": { "apex_analytic_m": 0.375, "apex_sim_m": 0.3733, "rel_error": 0.0043 } },
      "G6_energy":      { "passed": true, "detail": { "E0_J": 11.7703, "E_final_J": 0.981, "max_step_gain_J": 0.00019, "max_step_gain_allowed_J": 0.05885 } }
    }
  }
}
```

## Run C (venv + warp cache + pip cache wiped first)

### `bash judge/setup.sh` — exit 0, 1 m 55 s

```
$ time bash judge/setup.sh
[setup] creating venv at /home/user/.venvs/physx-drop-test
[setup] installing pinned wheels (sha256-verified via --require-hashes)
  Downloading ovphysx-0.6.3-py3-none-manylinux_2_35_x86_64.whl (139.0 MB)
  Downloading ovstage-0.2.0.377349-py3-none-manylinux_2_35_x86_64.whl (70.9 MB)
  Downloading newton_usd_schemas-0.5.0-py3-none-any.whl (22 kB)
  Downloading warp_lang-1.17.0-py3-none-manylinux_2_28_x86_64.whl (164.3 MB)
  Downloading numpy-2.2.6-cp312-cp312-manylinux_2_17_x86_64.manylinux2014_x86_64.whl (16.5 MB)
  Downloading packaging-23.2-py3-none-any.whl (53 kB)
Installing collected packages: packaging, ovstage, numpy, newton-usd-schemas, warp-lang, ovphysx
Successfully installed newton-usd-schemas-0.5.0 numpy-2.2.6 ovphysx-0.6.3 ovstage-0.2.0.377349 packaging-23.2 warp-lang-1.17.0

[notice] A new release of pip is available: 25.0.1 -> 26.2.1
[notice] To run: python3 -m pip install --upgrade pip
[setup] ovphysx native library loads: True
[setup] installed versions:
newton-usd-schemas==0.5.0
numpy==2.2.6
ovphysx==0.6.3
ovstage==0.2.0.377349
packaging==23.2
warp-lang==1.17.0
[setup] python: Python 3.12.15
[setup] done.

real	1m55.112s
user	0m32.425s
sys	0m11.747s
```

### `bash judge/grade.sh examples/good/scene.usda --json /tmp/vC.json` — exit 0, 20.6 s

```
$ time bash judge/grade.sh examples/good/scene.usda --json /tmp/vC.json
[grade] exit code: 0 (0 = all gates passed)

real	0m20.562s
user	0m6.944s
sys	0m2.999s
```

Verdict JSON is byte-identical to run A's (checked with
`json.dumps(..., sort_keys=True)` after removing `timing` and `seed`;
`timing.wall_seconds: 20.152`).

### `bash judge/selftest.sh` — exit 0, 2 m 00 s

```
$ time bash judge/selftest.sh
[selftest] 1/4 known-good scene must pass
[selftest]   ok (all gates passed)
[selftest] 2/4 known-bad mutants must each fail
[mutants] wrote 7 single-edit mutants to /tmp/physx-selftest.IFiWbF/mutants
[selftest]   killed:   cm-units  (failed: G4_resting)
[selftest]   killed:   gravity-flip  (failed: G2_freefall, G3_contact_time, G4_resting, G6_energy, G5_bounce_apex)
[selftest]   killed:   mass-zero  (failed: G1_loads)
[selftest]   killed:   no-ground-collision  (failed: G2_freefall, G3_contact_time, G4_resting, G5_bounce_apex)
[selftest]   killed:   no-rigidbody  (failed: G2_freefall, G3_contact_time, G4_resting)
[selftest]   killed:   restitution-over-unity  (failed: G3_contact_time, G5_bounce_apex)
[selftest]   killed:   spawn-inside-ground  (failed: G2_freefall, G3_contact_time, G6_energy)
[selftest] 3/4 kill rate: 7/7 = 100%
[selftest] 4/4 determinism (same seed, byte-identical JSON excl timing)
  identical
[selftest] PASS: judge kills 7/7 mutants, good passes, deterministic

real	2m0.225s
user	0m58.532s
sys	0m24.377s
```

## A vs C, side by side

| number | run A | run C |
|---|---|---|
| setup (from nothing) | exit 0, 2 m 22 s | exit 0, 1 m 55 s |
| selftest | exit 0, kill rate 7/7 = 100 % | exit 0, kill rate 7/7 = 100 % |
| grade | exit 0, 21.9 s (`timing` 21.269 s) | exit 0, 20.6 s (`timing` 20.152 s) |
| verdict `all_gates_passed` | true | true (byte-identical JSON) |
| box contact time (analytic 0.37773 s) | 0.375 s — Δ 0.65 frames | identical |
| ball contact time (analytic 0.47353 s) | 0.47083 s — Δ 0.65 frames | identical |
| ball bounce apex (analytic 0.375 m) | 0.3733 m — 0.43 % | identical |
| resting heights, both bodies | 0.100 m, error 0.0 mm | identical |
| fitted gravity (free fall), both | 9.81 | identical |
| max energy step gain (box / ball) | 0.02142 J / 0.00019 J | identical |

Only wall times differ (shared-machine noise); every physics number is
identical, as the determinism gate requires.

## `run.py` verification (no API key in this sandbox)

`python3 -m py_compile cookbook/physx-drop-test/run.py` — OK, exit 0.

run.py cannot be exercised end-to-end from inside this sandbox (creating
agent-next sandboxes needs `SBX_API_KEY`; the lead runs it end to end).
Its exact in-sandbox command sequence was executed directly against a
fresh clone of this repo at ref `sbx/demo-physx-drop-test`:

```
$ git clone --depth 1 -b sbx/demo-physx-drop-test https://github.com/agent-next/sandbox repo   # 2.5 s, exit 0
$ cd repo/cookbook/physx-drop-test
$ bash judge/setup.sh                       # exit 0
$ bash judge/grade.sh examples/good/scene.usda --json /tmp/verdict.json   # exit 0, all_gates_passed: true
```

## Tool versions installed (both runs)

`judge/VERSIONS.txt` (recorded by `judge/versions.sh`): python 3.12.15,
ovphysx 0.6.3, ovstage 0.2.0.377349, newton-usd-schemas 0.5.0,
warp-lang 1.17.0, numpy 2.2.6, packaging 23.2 — all sha256-verified by
`pip install --require-hashes` from `judge/requirements.txt`.

## Deviations

- **Two fresh *sandboxes* → two from-nothing installs in one sandbox.**
  The standard asks for two runs from two fresh sandboxes. This demo was
  built *inside* a disposable sandbox without an API key, so a second
  sandbox could not be created from here; instead run C wiped the venv,
  the warp kernel cache and pip's HTTP cache and re-downloaded /
  re-verified every wheel from PyPI. The lead's end-to-end `run.py`
  execution in a real agent-next sandbox is the independent cross-machine
  check; REPRODUCE.md (a different agent, post-merge, per the standard)
  will add a third.
- **Run A's pip download lines are partial** (output was piped through
  `tail`); the retained lines and the whole `[setup]` block are verbatim,
  and run C pastes a complete from-nothing install.
- **grade wall times vary ~20–22 s** between runs on this 2-vCPU box
  (shared-machine noise); all physics numbers are byte-identical, and
  only wall time lives under `timing`.
- pip's progress bars and its "new release of pip is available" notice
  were elided from the setup paste for width where pip drew them, and the
  `-r /home/user/w/cookbook/.../judge/requirements.txt` log paths in run
  A's paste are shortened to `.../judge/requirements.txt`; run C's pip
  lines are verbatim (piped output draws no bars).
- `(not done: media/ and REPRODUCE.md)` — per the standard these are a
  later task and an independent post-merge agent respectively.
