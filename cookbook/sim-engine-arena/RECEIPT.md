# sim-engine-arena demo — receipt

Real output from this builder sandbox (Debian, x86-64, CPython 3.12.15) and
from three fresh agent-next CPU sandboxes plus one 4 GiB GPU lease. Every
grade below ran with the default `--seed 0`. Commands run from the
repository root unless shown otherwise.

## Fresh-sandbox run 1 — `python3 cookbook/sim-engine-arena/run.py --ref sbx/arena-r2`

```
total: 63 s
sim-engine-arena demo: PASS
  gate agreement: pass
  gate run: pass
  gate structure: pass
  drop: ok  t_contact=0.4406 s (+0.11%)
  incline_slide: ok  a=1.6082 m/s^2 (+0.04%)
  incline_stick: ok  state=stick travel=1.8 mm
  pendulum: ok  T=2.0073 s (+0.00%)
  [grade] sbx exec 01a13c84-04fa-7741-9e04-14bf767632f3 ... ok (6 s)
  [kill]  sbx kill 01a13c84-04fa-7741-9e04-14bf767632f3 ... ok (2 s)
  [list]  sbx list ... ok (1 s)
cleanup: sandbox 01a13c84-04fa-7741-9e04-14bf767632f3 killed and confirmed gone
```

exit=0.

## Fresh-sandbox run 2 — same command, new sandbox

```
  [create]   sbx create --timeout-min ... ok (2 s)
  [clone]    sbx exec 01a13c86-4a61-72c0-8daa-1ee2ca1b1df0 ... ok (4 s)
  [setup]    sbx exec 01a13c86-4a61-72c0-8daa-1ee2ca1b1df0 ... ok (36 s)
  [selftest] sbx exec 01a13c86-4a61-72c0-8daa-1ee2ca1b1df0 ... ok (17 s)
  [grade]    sbx exec 01a13c86-4a61-72c0-8daa-1ee2ca1b1df0 ... ok (5 s)
  [kill]     sbx kill 01a13c86-4a61-72c0-8daa-1ee2ca1b1df0 ... ok (2 s)
total: 69 s
sim-engine-arena demo: PASS
  gate agreement: pass
  gate run: pass
  gate structure: pass
  drop: ok  t_contact=0.4406 s (+0.11%)
  incline_slide: ok  a=1.6082 m/s^2 (+0.04%)
  incline_stick: ok  state=stick travel=1.8 mm
  pendulum: ok  T=2.0073 s (+0.00%)
cleanup: sandbox 01a13c86-4a61-72c0-8daa-1ee2ca1b1df0 killed and confirmed gone
```

exit=0. The two runs' verdict JSONs are byte-identical except `timing`
(checked programmatically: `identical except timing: True`), and they match
the builder-local grade below value for value.

## Builder-local judge (same machine the repo was built on)

`bash cookbook/sim-engine-arena/judge/setup.sh` (cold — `~/.venvs/sim-engine-arena` deleted first):

```
setup.sh: creating venv at /home/user/.venvs/sim-engine-arena
Collecting mujoco==3.8.1 (from -r .../judge/requirements.lock (line 3))
  Using cached mujoco-3.8.1-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl (7.3 MB)
Collecting numpy==2.5.3 (from -r .../judge/requirements.lock (line 12))
  Using cached numpy-2.5.3-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl (16.7 MB)
...
Successfully installed absl-py-2.5.0 etils-1.14.0 fsspec-2026.9.0 glfw-2.10.0
mujoco-3.8.1 numpy-2.5.3 pyopengl-3.1.10 typing-extensions-4.16.0 zipp-4.1.0
setup.sh: ok

real    0m25.933s
exit=0
```

Idempotent second call: `setup.sh: venv already provides the pinned
toolchain` / `setup.sh: ok`, 2.7 s.

`bash cookbook/sim-engine-arena/judge/selftest.sh`:

```
selftest: generating mutants
selftest: grading known-good
selftest: known-good: PASS
selftest: mutant time_stretched: killed (gate: drop.csv_shape,incline_slide.csv_shape,incline_stick.csv_shape,pendulum.csv_shape)
selftest: mutant wrong_gravity: killed (gate: drop.oracle)
selftest: mutant friction_ignored: killed (gate: incline_slide.oracle,incline_stick.oracle)
selftest: mutant wrong_timestep: killed (gate: drop.csv_shape,incline_slide.csv_shape,incline_stick.csv_shape,pendulum.csv_shape)
selftest: mutant pendulum_length_off: killed (gate: pendulum.oracle)
selftest: mutant incline_sign_flip: killed (gate: incline_slide.oracle)
selftest: mutant crash: killed (gate: run)
selftest: mutant hardcoded_oracle: killed (gate: structure)
selftest: kill rate: 8/8 = 100%
selftest: determinism check (two grades of the good artifact)
selftest: determinism: OK
selftest: ok

real    0m16.761s
exit=0
```

`time bash cookbook/sim-engine-arena/judge/grade.sh cookbook/sim-engine-arena/examples/good/sim.py --seed 0`:

```
real    0m2.025s   exit=0
verdict timing: {"artifact_run_s": 0.9}; judge_intact: true
drop           t_contact_err 0.00114  (+0.11%, tol ±3%)
incline_stick  travel 0.00179 m  (stick, < 0.02 m)
incline_slide  accel_err   0.00037  (+0.04%, tol ±5%)
pendulum       period_err  4.36e-08 (+0.00%, tol ±2%)
agreement      max_dev 0.0 on all four scenarios (see Deviations)
```

## `run.py --gpu` — fresh sandbox + 4 GiB GPU lease (ref sbx/arena-r2)

```
  [create]   sbx create --timeout-min ... ok (2 s)
  [clone]    sbx exec 01a13c97-f351-7392-8e62-4b399c42e28d ... ok (3 s)
  [setup]    sbx exec 01a13c97-f351-7392-8e62-4b399c42e28d ... ok (24 s)
  [selftest] sbx exec 01a13c97-f351-7392-8e62-4b399c42e28d ... ok (15 s)
  [grade]    sbx exec 01a13c97-f351-7392-8e62-4b399c42e28d ... ok (4 s)
cleanup: sandbox 01a13c97-f351-7392-8e62-4b399c42e28d killed and confirmed gone
gpu: creating lease (4 GiB VRAM slice)...
gpu: lease gl-951d38-15 created (9 s)
gpu: running mujoco_warp replay (warp kernels cold-compile ~25 s per fresh lease; that is setup time, not sim time)...
gpu: exec round trip 117 s (HTTP 200)
gpu: destroying lease gl-951d38-15...
gpu: lease gl-951d38-15 deleted; GET confirms gone (404)
total: 194 s
sim-engine-arena demo: PASS          (CPU gates unchanged; exit=0)
```

GPU lane summary lines (lease versions verified on-lease, `lease_stack_ok: true`):

```
versions: mujoco 3.8.1, mujoco_warp 3.8.1, warp 1.13.0, python 3.13.5
  drop:           pass  t_contact=0.4396 s (-0.11% vs oracle)
  incline_stick:  pass  state=stick  travel=1.8 mm
  incline_slide:  pass  a=1.6081 m/s^2 (+0.05%)
  pendulum:       pass  T=2.0073 s (+0.00%)
```

The 117 s exec round trip includes the one-time warp kernel compile
(reported as setup time) plus the four replays; the simulations themselves
are ~13 k timesteps total. The GPU row is reported, never gating.

## Key numbers side by side

| quantity | builder-local grade | fresh sandbox run 1 | fresh sandbox run 2 | GPU lease replay | oracle (tolerance) |
|---|---|---|---|---|---|
| drop t_contact | 0.44059 s (+0.11 %) | 0.4406 s (+0.11 %) | 0.4406 s (+0.11 %) | 0.4396 s (−0.11 %) | 0.4401 s (±3 %) |
| incline_stick travel | 1.79 mm | 1.8 mm | 1.8 mm | 1.8 mm | < 20 mm |
| incline_slide accel | 1.60825 m/s² (+0.04 %) | 1.6082 (+0.04 %) | 1.6082 (+0.04 %) | 1.6081 (+0.05 %) | 1.6088 m/s² (±5 %) |
| pendulum period | 2.0073204 s (+4e-6 %) | 2.0073 s (+0.00 %) | 2.0073 s (+0.00 %) | 2.0073 s (+0.00 %) | 2.0073 s (±2 %) |
| kill rate | 8/8 = 100 % | (selftest inside run.py) | 8/8 (selftest step) | n/a | ≥ 90 % |
| determinism | OK | verdicts identical except `timing` | identical | n/a | required |

## Tool versions (what setup.sh actually installed)

`judge/VERSIONS.txt`:

```
## python 3.12.15, mujoco 3.8.1, numpy 2.5.3
absl-py==2.5.0
etils==1.14.0
fsspec==2026.9.0
glfw==2.10.0
mujoco==3.8.1
numpy==2.5.3
pip==25.0.1
PyOpenGL==3.1.10
typing_extensions==4.16.0
zipp==4.1.0
```

GPU lease image (read on-lease by the job): Python 3.13.5, mujoco 3.8.1,
mujoco-warp 3.8.1, warp-lang 1.13.0 — matching the pins setup.sh installs,
so the CPU judge and the GPU replay run the same engine version.

## Deviations

- **GPU exec quirks found and fixed during this build (commit 3aa7a59).**
  The first `--gpu` attempt failed: the exec endpoint runs each job with
  cwd `/` (read-only) and returns a crashed job as HTTP 409 with the
  reason in the body, which run.py discarded and retried as if transient;
  the tar also kept the builder's uid/gid so the extracted MJCF files were
  unreadable on the lease. run.py now normalizes tar members, extracts
  under `$HOME`, and fails fast, naming the job's error, instead of
  burning retries on a deterministic failure.
- **Gate 5 reads 0.0 for the known-good example** because the good port and
  the judge's reference port (`judge/ref_sim.py`) build the same MJCF
  scenes; the gate is discriminating for anything else (each mutant's
  trajectory deviates, and an agent-written port never matches the
  reference point for point).
- **The independent reproduction** (REPRODUCE.md) ran on the same builder
  machine, so its local-judge steps reused the warm venv (setup 1.7 s, not
  the 26 s cold path); its fresh-sandbox run is fully independent.
- The sandbox `list`-confirmation step took 19 s once (run by the
  reproducer); every other run saw 1–6 s. No cleanup ever failed to
  confirm.
