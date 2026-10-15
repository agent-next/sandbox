# Second panel recut, planned before rendering

All pre-end-card frames are native, moving MuJoCo 3D output. A cyan HUD
progress line animates through each shot. All video text is at least
60 px (44 px cap height), including provenance. No technical mutant
identifiers or unexplained “judge” appear in the video.

| Time | Real rendered content | Caption / evidence |
|---|---|---|
| 0–2 s | Native 3D orbit of the finished verified CPU reference | 25.8× CPU; 686,725 steps/s; 8,192 worlds; CPU replay of GPU run |
| 2–4 s | One CPU visual-replay world, arm reaching and boxes falling | 1 world measured; 134 steps/s |
| 4–6 s | Four differently started worlds, camera orbit | 64 worlds measured; 10,785 steps/s |
| 6–8 s | Sixteen differently started worlds, diagonal orbit | 512 worlds measured; 77,008 steps/s |
| 8–10 s | Sixty-four differently started worlds, dark matte floor, overhead orbit | 2,048 worlds measured; 248,064 steps/s |
| 10–12 s | 256 differently started worlds in one lit perspective scene | 8,192 worlds measured; 686,725 steps/s |
| 12–15 s | Exact CPU reference task, restrained slate studio floor | Reach. Drop. Settle.; all eight boxes land; 3.75× slow |
| 15–20 s | CPU reference vs retained GPU world-0 states, identical replay clock | 26,574 vs 686,725 steps/s, common-scale bars; CPU-rendered replays; GPU poses from 1-world recording; 6.25× slow |
| 20–24 s | Moving exact reference beside first four rejected configs | Red X: Fake results, Flipped gravity, No contact limit, Tiny time step; green check: 6/6 checks pass |
| 24–28 s | Opposite-angle moving reference beside remaining rejected configs | Red X: Stops too soon, Weak solver, Contact overflow, Out of memory; measured CPU/GPU error 0.00811 < 0.05 rad |
| 28–30 s | The only static end card, finished real 3D render | `python3 run.py --gpu`; From cookbook/gpu-sim-sweep |

## Measured versus visual replay

`run.py` invokes `judge/_sweep.py:gpu_point`, which copies one `MjData`
into all GPU worlds, with **identical initial states**. No retained varied
GPU footage exists. The scale shots therefore use the owner's permitted
alternative, not a claim about the measured trajectories:

- Every frame from 2–12 s explicitly says **“visual replay, perturbed
  starts”** and **“CPU render · not measured worlds”**.
- `render.py:visual_replay` runs new, deterministic CPU simulations of the
  same scene, timestep, solver and controls. Seed 0 adds small initial
  arm-angle and box-position/orientation perturbations. No poses are
  interpolated, drawn, or synthesized without physics.
- Up to 256 real simulated worlds are rendered, not 8,192. World-count
  headlines and fixed throughput values say **measured** and cite the
  original acceptance run. They are not a live performance meter.
- Instances translate native MuJoCo geometry only for display; arm
  colours vary for visual separation. The floor and lights remain dark
  in every scale shot, including 2,048 worlds, avoiding the old whiteout.
- `data/visual-replay.json` records the seed, perturbation bounds,
  trajectory hash and explicit `measured: false` provenance.

Everything outside that labelled scale visualization uses the unchanged
reference trajectory or actual retained GPU samples. `evidence.py`
reconstructs all 801 CPU states through the judge's `cpu_reference`,
checking the graded CPU oracle at 1e-9. GPU samples from the first ladder
point are rendered without interpolation, at the same clock as CPU,
with the judge's original CPU-i/GPU-i+1 convention and 0.05 tolerance.
The comparison shows the measured top aggregate rate, not single-world
speed or rendering speed. Each rendered pose is checked at 1e-9 against
its own source trajectory. Native 3D camera motion is not a pan over a
still. Proof replays are 5× slow; sweep replays are 2.5× slow.

All measured values and rejection outcomes still trace to the 2026-10-15
acceptance command, seed 0:
`python3 run.py --ref sbx/sweep-r4 --gpu --report-json media/data/report.json`.
No measured config, judge, receipt number or throughput is changed.
