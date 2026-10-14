# RECEIPT — control-tuning

All output below is real, pasted from a run in a disposable agent-next
Debian 12 sandbox (2 vCPU, ~4 GB RAM, Python 3.12.15, gcc 12.2.0,
2026-10-14). `run.py` itself was verified by `python3 -m py_compile` and by
executing the exact `sbx exec` command sequence locally (see "run.py
verification"); the lead's end-to-end `run.py` run will produce its own
numbers.

## 1. `bash judge/setup.sh` (fresh install)

```
control 0.10.2
slycot 0.7.0
numpy 2.2.6
scipy 1.15.3
setup: ok

real	0m22.775s
user	0m19.122s
sys	0m3.078s
exit=0
```

Idempotent second run:

```
setup: already installed at /home/user/ct-judge-venv (delete it to re-install)
control 0.10.2
slycot 0.7.0
numpy 2.2.6
scipy 1.15.3
setup: ok

real	0m1.524s
user	0m1.517s
sys	0m0.194s
exit=0
```

Every wheel in `judge/requirements.txt` is installed via
`pip install --require-hashes` (sha256 of the exact cp312/manylinux wheel
recorded in the file; a hash mismatch aborts the install). Versions pinned:
control 0.10.2, slycot 0.7.0, numpy 2.2.6, scipy 1.15.3,
matplotlib 3.10.8 (+ its pinned transitive deps).

## 2. `bash judge/selftest.sh`

```
== good example ==
PASS (expected pass): /home/user/w/cookbook/control-tuning/examples/good/controller.json
== known-bad mutants ==
PASS (expected reject): degenerate-r-force
PASS (expected reject): degenerate-r-torque
PASS (expected reject): nan-weight
PASS (expected reject): sign-flip
PASS (expected reject): too-aggressive
PASS (expected reject): too-sluggish
PASS (expected reject): wrong-shape
PASS (expected reject): wrong-type
== kill rate: 8/8 = 100% ==

real	1m17.063s
user	1m17.297s
sys	0m1.467s
exit=0
```

Kill rate 8/8 = 100 % (threshold 90 %). Selftest grades with `--no-mc`
(the Monte-Carlo gate is deterministic for a fixed seed and is covered by
the full grade below; dropping it keeps the selftest under 90 s).

## 3. `bash judge/grade.sh examples/good/controller.json --json /tmp/v.json`

```
verdict: PASS (18 gates, Monte-Carlo 200/200)

real	0m25.450s
user	0m25.098s
sys	0m0.234s
exit=0
```

Key numbers from `/tmp/v.json` (all 18 gates pass, `mc_seed 20260101`):

```
design_stable            -0.6523      pass=True
s1_F_demand_max_N        0.3453       pass=True
s1_tau_demand_max_Nm     0.5024       pass=True
s1_theta_overshoot       0            pass=True
s1_theta_settle_s        0.7          pass=True
s1_x_settle_s            1.52         pass=True
s1_theta_end_rad         1.195e-06    pass=True
s1_x_end_m               3.302e-06    pass=True
s2_peak_theta_rad        0.01941      pass=True
s2_F_demand_max_N        0.9024       pass=True
s2_tau_demand_max_Nm     0.1391       pass=True
s2_x_settle_s            6.05         pass=True
s2_theta_end_rad         4.127e-05    pass=True
gm_force_db              99           pass=True
pm_force_deg             59.12        pass=True
gm_torque_db             99           pass=True
pm_torque_deg            67.42        pass=True
mc_pass_fraction         1            pass=True
mc_pass 200 / mc_n 200
```

`gm_*_db = 99` is the judge's sentinel for "phase never crosses -180 deg in
the 0.01–1000 rad/s sweep" (gain margin unlimited).

## run.py verification

`python3 -m py_compile run.py` — clean. The sandbox-internal command
sequence run.py sends (`sbx exec --timeout 1200 <id> -- <cmd>` with, in
order: `git clone --depth 1 -b <ref> https://github.com/agent-next/sandbox
/home/user/sandbox-src`, `judge/setup.sh`, `judge/selftest.sh`,
`judge/grade.sh <good artifact> --json /tmp/verdict.json`,
`cat /tmp/verdict.json`) was executed locally via `bash -c` on a fresh clone
of this branch: clone 0.0 s, setup 22.8 s, selftest 87 s, grade 25.6 s,
verdict `passed: true`, 18 gates, Monte-Carlo 200/200, exit 0. The `sbx
create/exec/kill/list` calls match `cli/src/sbx/cli.py` at this ref
(`exec` has a 60 s default command timeout, hence `--timeout 1200` per
step; `kill` then `list` re-check to confirm the id is gone).

## Deviations

- `run.py` end-to-end with real `sbx` calls: (not done here — sandboxes
  cannot be created from inside this sandbox; the lead runs it. Verified by
  py_compile + local replay of the exact command sequence, as above.)
- Monte-Carlo gate never fails in practice for sane LQR designs (LQR has
  guaranteed stability margins); it is a required-to-hold robustness
  property, while the mutant kill rate is carried by the deterministic
  gates (saturation demand, settling, validation, lqr failure).
- Gain margins for this design are unlimited at the loop-at-a-time cut; the
  judge reports the sweep-band sentinel 99 dB rather than `Infinity`, which
  is not valid JSON.
- Selftest grades with `--no-mc` for speed; the committed grade run above
  includes the full Monte-Carlo.
- `matplotlib` (pinned 3.10.8) is installed only because `import control`
  needs it; the judge never plots.
