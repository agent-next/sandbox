# CPU verification, 2026-10-14

**PARTIAL, not an accepted demo.** Setup and unit/schema checks pass. No real
HDR frame has returned, so `examples/good/scene.json` is a candidate, not a
verified good example. No physical gate, convergence slope or full mutant
kill rate is claimed.

Implementation: `8c3c5af` on `sbx/demo-render-pathtrace`.
Physical attempts below used the preceding implementation revisions noted
below. Later fixes record adapter architecture and bound a stalled process
tree; they do not alter light transport.
Documentation-only commits may follow these code revisions.
All setup, browser, render, judge and test commands ran in real CPU sandboxes.
The workstation only edited/committed files and managed leases.
No media was produced.

## Setup

Command, in a fresh CPU sandbox:

```sh
sh judge/setup.sh
```

Real output tail (20 s; exit 0):

```text
MuTracer 0.1.1 SHA-512 and SHA-256 verified
Python 3.12.15
Playwright 1.63.0
Chromium 153.0.8010.12
numpy 2.2.6
MuTracer 0.1.1 (MIT)
MuTracer SHA-256 a84ec7913ae95e49b1172ea0cba45f20179f4a5d0cce08768d4812348e3e7b4a
setup PASS
```

Idempotent rerun with executable `./judge/setup.sh`, real output tail:

```text
MuTracer 0.1.1 SHA-512 and SHA-256 verified
Python 3.12.15
Playwright 1.63.0
Chromium 153.0.8010.12
numpy 2.2.6
MuTracer 0.1.1 (MIT)
MuTracer SHA-256 a84ec7913ae95e49b1172ea0cba45f20179f4a5d0cce08768d4812348e3e7b4a
setup PASS
idempotent_setup_exit=0 seconds=3
```

The direct adapter probe, launched with the CPU driver's Chromium flags,
returned:

```text
{'vendor': 'google', 'architecture': 'swiftshader', 'device': '', 'description': ''}
```

This proves adapter availability, **not rendering correctness**. MuTracer
reports its short adapter name as `google`; the driver therefore checks the
architecture as well, rather than incorrectly requiring the vendor string
to contain `swiftshader`.

## Unit and preflight tests

Command:

```sh
$HOME/.local/share/render-pathtrace/venv/bin/python -m unittest discover -s judge -p test_contract.py
```

Real output tail, exit 0:

```text
----------------------------------------------------------------------
Ran 11 tests in 0.034s

OK
```

These include synthetic positive/negative furnace and convergence fixtures,
HDR hash/seed logic, software-adapter identification and mocked runner cleanup.
Fixture output mentioning `PASS` is not a real render pass.
The final deadline regression also uses a mock, not a 595 s sleep.
The same sandbox command printed `py_compile_exit=0` and `unit_exit=0`.

Six actual `judge/grade.sh` subprocesses on scripted mutants returned:

```text
SCHEMA energy_gain exit=1 {"error": "AssertionError: number outside [0, 1]", "error_kind": "artifact", "gates": {}, "judge_unchanged": true, "pass": false, "requested_backend": "cpu", "seed": 17, "timing": {"total_seconds": 0.014}}
SCHEMA hidden_emission exit=1 {"error": "AssertionError: G2: undeclared emission", "error_kind": "artifact", "gates": {}, "judge_unchanged": true, "pass": false, "requested_backend": "cpu", "seed": 17, "timing": {"total_seconds": 0.006}}
SCHEMA clipping skipped: requires real HDR render
SCHEMA one_sample exit=1 {"error": "AssertionError: spp budget", "error_kind": "artifact", "gates": {}, "judge_unchanged": true, "pass": false, "requested_backend": "cpu", "seed": 17, "timing": {"total_seconds": 0.005}}
SCHEMA inside_sphere exit=1 {"error": "AssertionError: camera inside sphere", "error_kind": "artifact", "gates": {}, "judge_unchanged": true, "pass": false, "requested_backend": "cpu", "seed": 17, "timing": {"total_seconds": 0.011}}
SCHEMA nan_material exit=1 {"error": "ValueError: non-finite JSON: NaN", "error_kind": "artifact", "gates": {}, "judge_unchanged": true, "pass": false, "requested_backend": "cpu", "seed": 17, "timing": {"total_seconds": 0.006}}
SCHEMA resolution exit=1 {"error": "AssertionError: number outside [64, 128]", "error_kind": "artifact", "gates": {}, "judge_unchanged": true, "pass": false, "requested_backend": "cpu", "seed": 17, "timing": {"total_seconds": 0.005}}
6/6 schema mutants rejected; full 7-mutant kill rate not measured
```

These are input-validation checks. They do not establish the required >=90%
physical-judge kill rate.

## Real render attempts

Every attempt used seed 17 and
`sh judge/grade.sh examples/good/scene.json --seed 17`.
All failed inside G1 before returning an HDR buffer.

| attempt | measured total seconds | exit | result |
| --- | ---: | ---: | --- |
| 120 s offline-stage cap | 125.806 | 1 | stage timeout |
| 300 s offline-stage cap | 306.199 | 1 | stage timeout |
| temporary Dawn `disable_robustness` experiment | 307.892 | 1 | stage timeout; option not retained |
| bevelSamples=1, 300 s cap | 458.804 | 1 | stage timeout, including slow cleanup |
| 16×8 sphere geometry, 550 s cap (`21c7e8c`) | 306.734 | 1 | WebGPU device lost |
| disabled GPU watchdog (`15fb217`) | 429.557 | 1 | WebGPU device lost |

The last attempt's real output was:

```text
Running G1
{"adapter": "google", "backend": "webgpu", "chromium": "153.0.8010.12", "error": "Error: Page.evaluate: Error: WebGPU device lost (unknown): A valid external Instance reference no longer exists.\n    at http://localhost:43595/dist/mutracer.umd.js:13253:20761", "error_kind": "renderer", "gates": {}, "judge_unchanged": true, "pass": false, "requested_backend": "cpu", "seed": 17, "timing": {"total_seconds": 429.557}}
```

A WebGL fallback attempt and two unmonitored fresh reproduction leases
became unavailable before their final logs could be collected. Their cause
is unconfirmed; no exit code or render result is inferred from lease loss.
Later reproduction leases receive periodic exec probes.

## Two fresh monitored runs

Both cloned `15fb217` from the pushed branch and ran, in order:

```sh
sh judge/setup.sh
sh judge/selftest.sh --seed 17
sh judge/grade.sh examples/good/scene.json --seed 17 --json /tmp/verdict.json
```

Both setup logs ended with the version/integrity block pasted above. Periodic
exec probes kept these leases available until their results were captured.

| step | A exit / wall seconds | B exit / wall seconds |
| --- | --- | --- |
| setup | 0 / 18 | 0 / 17 |
| self-test | 1 / 411 | 1 / 391 |
| grade | 1 / 317 | 1 / 511 |
| physical gates completed | 0 | 0 |
| full kill rate | not measured | not measured |
| G1 means / G3 slope | unavailable | unavailable |
| actual backend / short adapter name | webgpu / google | webgpu / google |

Run A, real step output:

```text
setup exit=0 seconds=18
selftest exit=1 seconds=411
grade exit=1 seconds=317
```

Run A, real self-test output:

```text
Running G1
GOOD {"adapter": "google", "backend": "webgpu", "chromium": "153.0.8010.12", "error": "Error: Page.evaluate: Error: WebGPU device lost (unknown): A valid external Instance reference no longer exists.\n    at http://localhost:32827/dist/mutracer.umd.js:13253:20761", "error_kind": "renderer", "gates": {}, "judge_unchanged": true, "pass": false, "requested_backend": "cpu", "seed": 17, "timing": {"total_seconds": 409.583}}
{"kill_rate": null, "reason": "good control failed; mutant and determinism results not valid", "selftest_pass": false, "timing": {"total_seconds": 410.659}}
```

Run A, real grade output:

```text
Running G1
{"adapter": "google", "backend": "webgpu", "chromium": "153.0.8010.12", "error": "Error: Page.evaluate: Error: WebGPU device lost (unknown): A valid external Instance reference no longer exists.\n    at http://localhost:45317/dist/mutracer.umd.js:13253:20761", "error_kind": "renderer", "gates": {}, "judge_unchanged": true, "pass": false, "requested_backend": "cpu", "seed": 17, "timing": {"total_seconds": 315.587}}
```

Run B, real step output:

```text
setup exit=0 seconds=17
selftest exit=1 seconds=391
grade exit=1 seconds=511
```

Run B, real self-test output:

```text
Running G1
GOOD {"adapter": "google", "backend": "webgpu", "chromium": "153.0.8010.12", "error": "Error: Page.evaluate: Error: WebGPU device lost (unknown): A valid external Instance reference no longer exists.\n    at http://localhost:38905/dist/mutracer.umd.js:13253:20761", "error_kind": "renderer", "gates": {}, "judge_unchanged": true, "pass": false, "requested_backend": "cpu", "seed": 17, "timing": {"total_seconds": 390.03}}
{"kill_rate": null, "reason": "good control failed; mutant and determinism results not valid", "selftest_pass": false, "timing": {"total_seconds": 391.249}}
```

Run B, real grade output:

```text
Running G1
{"adapter": "google", "backend": "webgpu", "chromium": "153.0.8010.12", "error": "Error: Page.evaluate: Error: WebGPU device lost (unknown): A valid external Instance reference no longer exists.\n    at http://localhost:37033/dist/mutracer.umd.js:13253:20761", "error_kind": "renderer", "gates": {}, "judge_unchanged": true, "pass": false, "requested_backend": "cpu", "seed": 17, "timing": {"total_seconds": 508.666}}
```

The identical failure class is reproducible; the wall times vary. No numeric
agreement between rendered images can be assessed without returned HDR data.
The later adapter/deadline fixes passed unit tests but were not subjected to
another fresh full render sequence within the task budget.

## Outstanding acceptance

- G1 measured furnace means/variances/background errors: (not done: no HDR frame).
- G1 wrong-albedo **real-render** rejection: (not done: no HDR frame).
- G2 measured energy means: (not done: no HDR frame).
- G3 real RMSE levels/slope: (not done: no HDR frame).
- G4 byte-identical real HDR hashes and repeated verdict comparison:
  (not done: no HDR frame).
- G5 measured good-scene bands/noise and accepted candidate:
  (not done: no HDR frame; SPEC targets remain provisional).
- Full self-test kill rate: (not done: no passing good control).
- `run.py` end-to-end create/clone/kill: (not done: assigned to the lead).
  Its modules compile and cleanup behavior is unit-tested; the remote command
  sequence is exercised directly instead of nesting sandbox creation.
- Independent other-model reproduction: (not done: not dispatched).
- Media: (not done: explicitly deferred by the owner).

## Deviations

1. Owner-pinned MuTracer 0.1.1 was published 2026-10-14, inside the standard's
   two-week exclusion window. Its supplied npm SHA-512 integrity and recorded
   SHA-256 are checked before extraction; it runs only in disposable sandboxes.
2. Playwright/Chromium come from the sandbox image. Setup verifies exact
   versions and fails when absent/mismatched instead of downloading replacements.
3. Numeric G5 targets are engineering targets, not calibrated limits from a
   passing example. No acceptance or completed-demo claim is made.
4. The cookbook index is not updated because it lists reviewed demos.
5. Two fresh successful runs and independent reproduction remain pre-merge
   blockers. Media is excluded from this task by explicit instruction.
