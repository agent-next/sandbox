# sim-engine-arena — independent reproduction

Recorded by a separate agent (not the demo's builder), following **only**
`cookbook/sim-engine-arena/README.md` from a fresh shallow clone of
`https://github.com/agent-next/sandbox` at ref `sbx/arena-r2`. No other
demo file was read beforehand; nothing was committed by the reproducer.
Environment: Python 3.12.15, `SBX_API_KEY` exported, CPU only (no GPU
lease created; only sandboxes the reproducer itself created were touched).
Commands as written in the README, run from the repository root.

| step | command | exit | wall | key numbers |
|---|---|---|---|---|
| setup | `bash cookbook/sim-engine-arena/judge/setup.sh` | 0 | 1.7 s | venv already pinned → reused (cold path not exercised here) |
| selftest | `bash cookbook/sim-engine-arena/judge/selftest.sh` | 0 | 12.4 s | known-good PASS; kill rate **8/8 = 100 %**; determinism OK |
| grade | `bash cookbook/sim-engine-arena/judge/grade.sh cookbook/sim-engine-arena/examples/good/sim.py` | 0 | 2.3 s | all gates pass, `judge_intact: true`, seed 0 |
| one-command run | `python3 cookbook/sim-engine-arena/run.py --ref sbx/arena-r2` | 0 | 65.7 s | sandbox `01a13c99-bfbc-7091-9f53-8e939a1a062f` killed and confirmed gone |

Grade detail (seed 0, tolerances from SPEC.md):

- drop: t_contact = 0.44059 s, +0.11 % (tol ±3 % of 0.4401 s); penetration 30.2 mm, rebound 0.0 m
- incline_stick: state stick, travel 1.79 mm (limit < 20 mm)
- incline_slide: a = 1.60825 m/s², +0.04 % (tol ±5 % of 1.6088); travel 0.8012 m
- pendulum: T = 2.0073204 s, err 4.4e-8 (tol ±2 % of 2.0073); energy drift 3.6e-4
- agreement: max_dev 0.0 on all four scenarios (the known-good artifact and
  the judge's reference port build the same MJCF scenes — see RECEIPT.md
  "Deviations"; the gate is discriminating for agent-written ports and mutants)

One-command run, per-step timings printed by run.py: create 2 s, clone 3 s,
setup 23 s, selftest 12 s, grade 3 s, cat 2 s, kill 1 s, list-confirm 19 s,
total 65 s. Final summary: `sim-engine-arena demo: PASS` — drop
t_contact=0.4406 s (+0.11 %), incline_slide a=1.6082 m/s² (+0.04 %),
incline_stick stick 1.8 mm, pendulum T=2.0073 s (+0.00 %).

Every README headline number reproduced within the SPEC tolerances: 8/8
kill rate, determinism OK, all four oracles met with 1–2 orders of
magnitude of margin, cleanup confirmed.

Cold-start frictions found (fixed in the README after this run):

1. The "try the judge locally" block did not say to run from the repository
   root; from the demo directory, grade.sh resolves the artifact path
   relative to the CWD and fails structure with a path error. The README
   now states it.
2. The measured-timings paragraph mixed in-sandbox cold numbers with warm
   local numbers without labeling the environment; the README now labels
   both.
