# RoboSimStudio real2sim: recover a towel's hidden material parameters

A reference rollout of a RoboSimStudio towel fold was produced with **hidden**
material and contact parameters (bending and stretch stiffness, friction,
damping, the shell model, and the scene's contact-model choices). You get the
rendered video of that rollout, the scene file, the parameter table with units
and RSS's own declared ranges, and a grading command. Your agent proposes a
`params.json`; the judge re-simulates the scene with it on a **disposable RTX
5090 GPU slice** and returns five numeric gates. The physics is RoboSimStudio
on Newton — MuJoCo-Warp for the arms, VBD for the cloth — exactly the stack the
paper's Sec. 3 describes, at pinned SHAs, with the GPU lease destroyed and its
absence confirmed at the end of every run.

## Ask your agent

> You are given `examples/reference/reference.mp4` — a rendered video of a
> towel being folded by two robot arms in RoboSimStudio — plus the scene file
> (`judge/rollout.py` documents the scene), the editable-parameter table
> (`judge/params_table.json`) and the grading command
> (`cookbook/robosimstudio-real2sim/judge/grade.sh`). Produce
> `cookbook/robosimstudio-real2sim/params.json` — material and contact
> parameters inside the declared ranges — such that
> `judge/grade.sh params.json` passes all five gates. Iterate: propose,
> grade, read the JSON verdict, refine. The hidden parameters are ordinary
> fabric values; a real towel is neither cardboard nor a wet noodle.

## One-command run

From this repository's root, with Python 3.10+ (no extra packages) and
`SBX_API_KEY` (or `E2B_API_KEY`) on a key with GPU access:

```bash
export SBX_API_KEY=<your key>
python3 cookbook/robosimstudio-real2sim/run.py
```

The script creates the GPU lease, uploads the pinned RoboSimStudio wheelhouse
through the lease's exec payloads (the lease has no network), builds the
hidden reference, runs the judge self-test, grades the known-good artifact,
prints the verdict JSON, and always deletes the lease and confirms it is gone.
Non-zero exit on any failure, naming the lease id if cleanup could not be
confirmed. `--keep` leaves the lease up and prints its id.

Measured wall times per phase (2-vCPU CPU sandbox driving the lease, 2026-10-15):

| phase | wall time |
| --- | --- |
| lease create | ~10 s (can hit 409 under contention; retried) |
| wheelhouse upload (240 MB, 4 MB chunks) | ~40–55 min |
| pip install --no-index | ~10 s |
| Warp kernel cold-compile | ~25 s per fresh lease |
| reference build (2 tracks x 2 seeds) | rollout-time bound |
| judge self-test (good + 7 mutants) | 16 rollouts |
| cleanup + 404 confirm | ~1–11 s |

Why so much upload: the lease image ships warp-lang 1.13 / mujoco 3.8.1 /
newton 1.2, and newton 1.6 (what RSS pins) needs warp-lang >= 1.17 — measured,
not assumed: on the lease's own warp it dies at
`wp.config has no attribute 'log_level'` inside Newton's graph colouring. So
`warp-lang 1.18.0` (142 MB) has to travel in. A `robotsim` GPU template with
RSS baked in, or a file-upload route, would delete this phase; neither is live,
and nothing here depends on either.

## What the judge decides

Five gates, all numeric and seeded (details in SPEC.md): **G1** every parameter
is a real `ClothMaterialSpec` field inside its declared range; **G2** mean
per-particle position error on the training track <= 3x the error of the hidden
truth re-run under a different perturbation seed; **G3** the same on a held-out
arm track the agent never saw; **G4** the fold outcome (RSS's own fold measure)
lands in the reference's band; **G5** the rollout is finite, bounded, healthy.
`judge/selftest.sh` proves the judge can fail: good artifact passes, every
single-edit mutant fails, kill rate printed.

## Limits, stated plainly

- Only the towel scene (`examples/01_cloth/00_towel.py`'s) and material/contact
  recovery. The real robot, the smartphone video, force-feedback teleoperation,
  Graph-as-Policy and the SuperDex sponge are out of scope (the last because
  `superdex-physics` publishes cp312 wheels only and the lease is Python 3.13).
- Rendering is Newton's `tiled` backend, headless; the paper's OVRTX path
  tracer is not used.
- The reference video shown to the agent is rendered by RSS's own recorder;
  no imageio/ffmpeg work beyond what RSS already does.
- Grade rollouts run on the GPU lease; `judge/grade.py` shells out to
  `judge/rollout.py` there, so grading needs the lease, not just a laptop.
- The trajectory G2/G3 compare is the cloth's particle positions; the arm
  trajectory is given, not recovered.

## Citation

RoboSimStudio: An Interactive Toolkit for Rapid Real2Sim for Robot Manipulation
(arXiv 2610.18835). Code: https://github.com/robosimstudio/robosimstudio at
commit `73739abe212f963e8a9f5862b27bca370df091a7` (initial public commit),
Apache-2.0. Newton and Warp are NVIDIA's; MuJoCo is Google DeepMind's; both
ship their own licences.
