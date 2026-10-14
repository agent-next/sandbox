# Sim-to-real system identification on a GPU slice

A "real robot" rig — a box sliding across a table while a 2-link arm tracks a
step command — was recorded 10 times. Its MuJoCo model is right except for the
five contact and actuation parameters nobody measures on a real rig (sliding
friction `mu`, contact solref `timeconst` and damping ratio, hinge damping and
armature). An agent gets 6 of the recordings plus a batched GPU evaluate
tool — one `mujoco_warp` run per batch, one world per candidate × recording on
a 4 GiB RTX 5090 slice — and must return `params.json`. The judge it cannot
fool re-simulates the artifact with CPU MuJoCo 3.8.1 against 4 held-out
recordings the agent never saw (hidden ground truth, seed-derived, never on
disk where the artifact could read it), and finally re-scores the artifact on
a fresh GPU slice to require that the two engines agree.

A sandbox helps because the interesting part of sim-to-real ID is the size of
the search: hundreds of parameter candidates, each needing 6 forward
simulations of 500 steps. One batched GPU run scores generations of candidates
in the time the host CPU needs for a handful (measured below and in
RECEIPT.md), and the disposable slice with the exact pinned mujoco-warp stack
exists only for the duration of the run.

## One-command run

With Python 3.10+ and `SBX_API_KEY` exported (a key with GPU access):

```bash
python3 cookbook/sim-tuner/run.py
```

The command creates a fresh 4 GiB GPU slice lease over the agent-next REST
API (`POST /sandboxes {"accel":{"vram_gb":4,"reserve":"exec"}}`), ships the
demo to it, verifies the lease stack against the pinned
`judge/version-table.json`, runs the judge self-test (good artifact passes;
every scripted mutant fails), grades `examples/good/params.json`, prints the
verdict JSON, then deletes the lease and confirms it is gone (`GET` → 404).
Wall time is printed per step.

Limits, stated plainly: the judge needs GPU access on your key (the G4
agreement check creates a GPU slice; `--cpu-only` exists for judge
development and skips G4). The workload is small enough that a fast
multi-core CPU can brute-force it slowly — the point is the agent loop, not a
speedup record. MuJoCo is pinned to 3.8.1 on both engines; the judge records
what the lease actually serves and fails if it differs. See `SPEC.md` for the
exact gates and `RECEIPT.md` for real measured output.

## What the judge checks (short form)

| gate | rule |
|---|---|
| G1 ranges | strict JSON object, exactly the 5 parameters, finite, each within its physical range |
| G2 train error (reported) | CPU MuJoCo 3.8.1 RMS mismatch vs the 6 train recordings |
| G3 held-out error | CPU MuJoCo vs 4 hidden initial-condition recordings: `< 0.030` AND `< 30 %` of the default-parameter error |
| G4 GPU/CPU agreement | same artifact scored by one batched `mujoco_warp` run on a fresh 4 GiB slice: `|gpu − cpu| ≤ 0.003` and `≤ 10 %`; lease stack versions must match `judge/version-table.json` |

The acceptance oracle is hidden ground truth (generated from the seed at
grade time, never committed) plus a held-out split re-simulated by an
independent engine — never "the solver ran".

## Ask your agent

With the sandbox plugin installed, paste this prompt. The agent runs the
calibration loop itself in a sandbox and iterates with the judge until it
passes — that loop is the demo:

> Create a 4 GiB GPU lease (`POST https://api.sbx.agent-next.com/sandboxes`
> with `{"accel":{"vram_gb":4,"reserve":"exec"}}`, header
> `X-API-Key: $SBX_API_KEY`; files under `~` persist between execs; delete the
> lease when done and confirm with GET → 404). Read
> `cookbook/sim-tuner/SPEC.md` carefully: a box-and-arm rig was recorded, and
> five MuJoCo parameters (`mu`, `solref_tc`, `solref_dr`, `damping`,
> `armature`) must be calibrated from the 6 train recordings. Write a batched
> `mujoco_warp` evaluator on the lease (one world per candidate × recording,
> per-world model fields `geom_friction`, `geom_solref`, `dof_damping`,
> `dof_armature`; `nconmax=16`, `njmax=72`) and search — a broad uniform
> pre-sample first, then quasi-Newton (BFGS) descent with batched
> finite-difference gradients (one GPU chunk per gradient; the valley is
> narrow and diagonal, so population resampling alone stalls). When your best
> candidate scores well below
> the noise-floor band on the train split, submit it as `params.json` and grade
> it: `bash cookbook/sim-tuner/judge/grade.sh params.json --seed 7`. Iterate
> until every gate passes, then report the verdict JSON (held-out error and
> its fraction of the default error), delete the lease and confirm it is gone.
> If a gate will not pass, say exactly which one and what you tried, and stop.

## Layout

- `SPEC.md` — goal, gates, thresholds and their calibration, toolchain pins
- `judge/setup.sh` — pinned CPU-judge venv (sha256-locked); `--record` pins the
  reference GPU lease stack to `judge/version-table.json`
- `judge/grade.sh` — gates G1–G4, one JSON verdict, exit 0 only if all pass
- `judge/mutants.py`, `judge/selftest.sh` — 14+ known-bad artifacts, kill rate
  printed, determinism checked
- `examples/good/params.json` — produced by the builder's real GPU search loop
  (`tools/search.py`); every iteration's scores in `examples/good/loop.json`
- `run.py` — the one-command run above (stdlib only)
- `media/` — figures/video regenerated by `media/make_media.sh` from committed
  run data
