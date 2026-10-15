# sim-engine-arena — independent reproduction

Recorded on 2026-10-14 by GPT-6.1 (GPT model family), **not the builder**.
I followed only `cookbook/sim-engine-arena/README.md` from a fresh shallow
clone at ref `sbx/arena-r2`. I first read RECEIPT.md, SPEC.md, and the
existing REPRODUCE.md after all six demo attempts and their cleanup
checks were complete. I did not read judge source.

Environment: Python 3.12.3; Linux 6.14.0-27-generic. The optional GPU
replay reported Python 3.13.5.

All demo commands below ran from the repository root, unchanged except
for combining the README's documented `--gpu` and `--ref` options for
run 6. Each attempt created a different sandbox. The first three failed;
I then used the README's explicit branch override for two CPU repeats
and one GPU repeat. This reproduces the packaged demo, not a newly
written simulation port. The optional local-judge alternative and
interactive “Ask your agent” workflow were not exercised.

`runs.log` contains the complete captured command output, exit codes,
and externally measured wall times. Excerpts below are real output.

## Run 1 — default CPU command

| command | exit | wall | key numbers |
|---|---|---|---|
| `python3 cookbook/sim-engine-arena/run.py` | 1 | 18.419 s | drop t_contact, incline a, stick travel, pendulum T: not produced; gates not reached |

```text
bash: sandbox/cookbook/sim-engine-arena/judge/setup.sh: No such file or directory
  [setup] sbx exec 01a13cc9-8632-77c3-a502-9adf105d2ce0 ... exit 127 (3 s)
run.py: step setup failed in sandbox 01a13cc9-8632-77c3-a502-9adf105d2ce0 (exit 127)
cleanup: sandbox 01a13cc9-8632-77c3-a502-9adf105d2ce0 killed and confirmed gone
[exit_code=1; wall_seconds=18.419]
```

## Run 2 — same default command, fresh sandbox

| command | exit | wall | key numbers |
|---|---|---|---|
| `python3 cookbook/sim-engine-arena/run.py` | 1 | 18.136 s | drop t_contact, incline a, stick travel, pendulum T: not produced; gates not reached |

```text
bash: sandbox/cookbook/sim-engine-arena/judge/setup.sh: No such file or directory
  [setup] sbx exec 01a13ccb-573f-7273-a245-83cfa73fff93 ... exit 127 (3 s)
run.py: step setup failed in sandbox 01a13ccb-573f-7273-a245-83cfa73fff93 (exit 127)
cleanup: sandbox 01a13ccb-573f-7273-a245-83cfa73fff93 killed and confirmed gone
[exit_code=1; wall_seconds=18.136]
```

## Run 3 — documented GPU command, non-gating lane

| command | exit | wall | key numbers |
|---|---|---|---|
| `python3 cookbook/sim-engine-arena/run.py --gpu` | 1 | 9.226 s | drop t_contact, incline a, stick travel, pendulum T: not produced; CPU gates and GPU lane not reached |

```text
bash: sandbox/cookbook/sim-engine-arena/judge/setup.sh: No such file or directory
run.py: step setup failed in sandbox 01a13ccb-ec64-7220-a75b-169b5b0de3d9 (exit 127)
cleanup: sandbox 01a13ccb-ec64-7220-a75b-169b5b0de3d9 killed and confirmed gone
[exit_code=1; wall_seconds=9.226]
```

This was a CPU setup failure, not a failed GPU score.

## Run 4 — documented branch override, fresh CPU sandbox

| command | exit | wall | key numbers |
|---|---|---|---|
| `python3 cookbook/sim-engine-arena/run.py --ref sbx/arena-r2` | 0 | 40.312 s | drop t_contact 0.4405908164210919 s; incline a 1.608249455710321 m/s²; stick travel 0.00178852535729963 m; pendulum T 2.0073203848961487 s; all five gate categories pass |

```text
selftest: kill rate: 8/8 = 100%
selftest: determinism: OK
cleanup: sandbox 01a13ccc-6bdc-76f2-9061-abafdcbcb7be killed and confirmed gone
total: 40 s

sim-engine-arena demo: PASS
  gate agreement: pass
  gate run: pass
  gate structure: pass
  drop: ok  t_contact=0.4406 s (+0.11%)
  incline_slide: ok  a=1.6082 m/s^2 (+0.04%)
  incline_stick: ok  state=stick travel=1.8 mm
  pendulum: ok  T=2.0073 s (+0.00%)
[exit_code=0; wall_seconds=40.312]
```

## Run 5 — same branch override, second fresh CPU sandbox

| command | exit | wall | key numbers |
|---|---|---|---|
| `python3 cookbook/sim-engine-arena/run.py --ref sbx/arena-r2` | 0 | 42.554 s | drop t_contact 0.4405908164210919 s; incline a 1.608249455710321 m/s²; stick travel 0.00178852535729963 m; pendulum T 2.0073203848961487 s; all five gate categories pass |

```text
selftest: kill rate: 8/8 = 100%
selftest: determinism: OK
cleanup: sandbox 01a13cce-e6e1-7191-b0e4-750edf9c4635 killed and confirmed gone
total: 42 s

sim-engine-arena demo: PASS
  gate agreement: pass
  gate run: pass
  gate structure: pass
  drop: ok  t_contact=0.4406 s (+0.11%)
  incline_slide: ok  a=1.6082 m/s^2 (+0.04%)
  incline_stick: ok  state=stick travel=1.8 mm
  pendulum: ok  T=2.0073 s (+0.00%)
[exit_code=0; wall_seconds=42.554]
```

## Run 6 — GPU with the documented branch override

| command | exit | wall | key numbers |
|---|---|---|---|
| `python3 cookbook/sim-engine-arena/run.py --gpu --ref sbx/arena-r2` | 0 | 204.623 s | CPU: drop t_contact 0.4405908164210919 s; incline a 1.608249455710321 m/s²; stick travel 0.00178852535729963 m; pendulum T 2.0073203848961487 s; all five gate categories pass. GPU: drop 0.4396 s; incline a 1.6081 m/s²; stick 1.8 mm; pendulum T 2.0073 s; four replay passes, non-gating |

```text
selftest: kill rate: 8/8 = 100%
selftest: determinism: OK
cleanup: sandbox 01a13ccf-eec2-7cc1-94c5-b84a691f3b3e killed and confirmed gone
gpu: creating lease (4 GiB VRAM slice)...
gpu: lease gl-951d38-24 created (9 s)
gpu: running mujoco_warp replay (warp kernels cold-compile ~25 s per fresh lease; that is setup time, not sim time)...
gpu: exec round trip 150 s (HTTP 200)
gpu: destroying lease gl-951d38-24...
gpu: lease gl-951d38-24 deleted; GET confirms gone (404)
total: 204 s

sim-engine-arena demo: PASS
  gate agreement: pass
  gate run: pass
  gate structure: pass
  drop: ok  t_contact=0.4406 s (+0.11%)
  incline_slide: ok  a=1.6082 m/s^2 (+0.04%)
  incline_stick: ok  state=stick travel=1.8 mm
  pendulum: ok  T=2.0073 s (+0.00%)
  gpu lane (mujoco_warp replay; reported, never gating):
    lease versions: {'mujoco': '3.8.1', 'mujoco_warp': '3.8.1', 'warp': '1.13.0', 'python': '3.13.5'}
    drop: pass t_contact=0.4396 s
    incline_slide: pass a=1.6081 m/s^2
    incline_stick: pass state=stick travel=1.8 mm
    pendulum: pass T=2.0073 s
[exit_code=0; wall_seconds=204.623]
```

## Grade detail and comparison with RECEIPT.md

All three successful CPU verdicts have seed 0, `judge_intact: true`,
all four CSV-shape and oracle checks passing, and structure, run, and
agreement passing. Their parsed verdicts are identical after excluding
`timing`. Every self-test killed 8/8 mutants and passed determinism.

| quantity | RECEIPT CPU | reproduced CPU, runs 4–6 | SPEC tolerance / result |
|---|---|---|---|
| drop t_contact | 0.4406 s | 0.4405908164210919 s | ±3%; absolute oracle error 0.113615045%, pass |
| incline_slide a | 1.6082 m/s² | 1.608249455710321 m/s² | ±5%; absolute oracle error 0.036958688%, pass |
| incline_stick travel | 1.8 mm | 0.00178852535729963 m | < 0.02 m, pass |
| pendulum T | 2.0073 s | 2.0073203848961487 s | ±2%; absolute oracle error 0.000004358544%, pass |
| agreement max_dev | 0.0, all scenes | 0.0, all scenes | ≤ 5% of each scale, pass |
| mutant kill rate | 8/8 | 8/8, each successful run | ≥ 90%, pass |
| determinism | OK | OK | required, pass |

The slide also traveled 0.8012394925837607 m, exceeding SPEC's 0.1 m
minimum. Drop penetration was 0.030193652691982768 m, rebound 0.0 m;
pendulum energy drift was 0.00035511771080137306. Agreement is zero for
the supplied known-good example, as RECEIPT.md explains; this is not
evidence of independently authored port code.

The GPU's four displayed values match RECEIPT.md's GPU row exactly at
the reported precision. No higher-precision GPU values were emitted.
GPU success is reported, never a gate.

Programmatic comparison output:

```text
Successful CPU verdicts captured: 3
CPU verdicts identical except timing: True
CPU observed: t_contact=0.4405908164210919 s; a=1.608249455710321 m/s^2; stick_travel=0.00178852535729963 m; T=2.007320384896149 s
Match RECEIPT CPU displayed precision: True
CPU absolute oracle errors: drop=0.113615045% (limit 3%); slide=0.036958688% (limit 5%); pendulum=0.000004358544% (limit 2%)
All five gate categories pass; judge_intact=True; agreement max_dev=0.0 in all four scenes.
Selftest 8/8 lines: 3
Selftest determinism OK lines: 3
```

Wall times are not numerical-physics acceptance tolerances. The successful
CPU runs printed totals of 40 and 42 s, versus RECEIPT's 63 and 69 s.
The GPU run printed 204 s, versus its quoted receipt run's 194 s;
GPU exec round trip was 150 s versus 117 s. Nothing was adjusted to
force matching timings.

## Cleanup verification

After **each** attempt, I checked its own cleanup line and independently
ran `sbx list` before proceeding. None of the six created sandbox IDs
appeared in the subsequent list. For the GPU lease, the run reported
DELETE followed by GET 404; its ID was also absent from the final
independent list. Unrelated sandboxes/leases were left untouched.

The log audit printed:

```text
Run 1: cleanup line present; subsequent sbx list excludes created sandbox.
Run 2: cleanup line present; subsequent sbx list excludes created sandbox.
Run 3: cleanup line present; subsequent sbx list excludes created sandbox.
Run 4: cleanup line present; subsequent sbx list excludes created sandbox.
Run 5: cleanup line present; subsequent sbx list excludes created sandbox.
Run 6: cleanup line present; subsequent sbx list excludes created sandbox.
GPU displayed physics values match RECEIPT; all four replay scenes pass (non-gating).
GPU lease deletion confirmed by GET 404 and subsequent sbx list.
```

## README frictions found

1. **Installer assumes `pip` exists.** The README gives
   `pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"`.
   That exact command exited 127:

   ```text
   /bin/bash: line 1: pip: command not found
   [exit_code=127; wall_seconds=0.002]
   ```

   `python3 -m pip --version` also reported `No module named pip`.
   An existing `sbx` executable was available, so I used it without
   installing or changing packages. This did not validate the README's
   install path on a machine without the CLI.

2. **The headline CPU and GPU forms do not work with their default
   remote checkout.** The README gives
   `python3 cookbook/sim-engine-arena/run.py` as “CPU sandbox end-to-end”
   and `python3 cookbook/sim-engine-arena/run.py --gpu` as
   “+ optional mujoco_warp GPU replay”. Both CPU attempts and the GPU
   attempt failed because `judge/setup.sh` was absent in the sandbox.
   I had to use the README's third command,
   `python3 cookbook/sim-engine-arena/run.py --ref sbx/arena-r2`,
   labeled “other repository ref”. That override was necessary here,
   not merely optional. For the GPU repeat I combined the same
   documented `--ref` with `--gpu`. No code was patched.

Acquisition friction, not a README defect: the requested initial clone
timed out after 180 s. The allowed `gh repo clone` fallback first timed
out after 300 s; the identical fallback then completed with a longer
allowance. Exact wall time and numeric exit code for that background
clone were not captured; the branch and clean checkout were verified.

## Verdict

**Numbers match RECEIPT within SPEC tolerances: YES**, for the two fresh
CPU reproductions using the README's documented `--ref sbx/arena-r2`
command. The optional GPU replay also matches at its printed precision
and passes all four scenes.

**Unqualified headline-command reproduction: NO.** Both default CPU runs
and the default GPU attempt failed before grading. A documented branch
override was required.

No repository files were edited, committed, or pushed. The clone was
deleted after comparison; only this report and the sanitized `runs.log`
were retained in the reproduction directory.
