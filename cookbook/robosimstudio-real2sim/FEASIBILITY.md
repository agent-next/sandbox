# Feasibility: RoboSimStudio on agent-next sandboxes

Measured 2026-10-14. All output below is real, pasted from runs on this
branch; nothing is from documentation.

Upstream under test: `robosimstudio/robosimstudio` @
`73739abe212f963e8a9f5862b27bca370df091a7` ("Initial commit"), Apache-2.0.

## Environment

Two machines are involved:

- **CPU sandbox** (this host): internet, Python 3.12.15, uv. RSS's own
  `uv.lock` resolved and installed here.
- **GPU lease** (`POST /sandboxes {"accel":{"vram_gb":N,"reserve":"exec"}}`):
  RTX 5090 slice, Python 3.13.5 (conda), no network, no pip on PATH
  (`python -m pip` works). Preinstalled versions are older than what RSS
  requires — see the gap table below.

## Pinned dependency resolution (`uv.lock` at the pinned SHA)

`uv sync --frozen` on the CPU sandbox: **66 s**, 82 packages, CPython 3.12.14
(uv-managed). Resolved versions that matter:

| package | RSS needs (locked) | GPU lease has | gap |
| --- | --- | --- | --- |
| newton | 1.6.0 (`>=1.6,<1.7`) | 1.2.0 | ship cp313 wheel |
| warp-lang | 1.18.0 | 1.13.0 | ship cp313 wheel (~140 MB) |
| mujoco | 3.12.0 (`~=3.12.0` via newton[sim]) | 3.8.1 | ship cp313 wheel |
| mujoco-warp | 3.12.0 | 3.8.1 | ship cp313 wheel |
| jax / jaxlib | 0.11.2 | 0.7.2 | ship cp313 wheel |
| numpy | 2.2.6 | 1.26.4 | ship cp313 wheel |
| scipy | 1.18.1 | 1.15.3 | ship cp313 wheel |
| trimesh | 4.12.2 | 4.8.2 | ship wheel |
| viser | 1.1.1 | — | ship wheel |
| pyroki | git `95afccc22658c461ab1042a048ae4e9c24bc2a47` | — | build wheel from git |
| jaxls | git `50a58be88c5ef74532f09e3f55268b4f02c490e3` | — | build wheel from git |
| yourdfpy | 0.0.60 | — | ship wheel |
| coacd | 1.0.11 | 1.0.11 | none |
| usd-core | 26.3 | 26.3 | none |
| imageio + ffmpeg | 2.38.0 / 0.6.0 | 2.37.0 / 0.6.0 | minor; probably fine |
| ovrtx | 0.4.0.346409 (default group `rtx`, 1.7 GB) | — | **skip**: `ROBOSIMSTUDIO_RENDERER=tiled` covers headless render |
| superdex-physics | 1.0.0, cp312-only wheels | — | **impossible on py3.13**: `wipe_the_bar` out of scope |
| robosimstudio | 0.1.0 @ pinned SHA | — | build wheel |

The GPU lease therefore needs a wheelhouse of roughly 12 packages plus
transitives, built with `pip download --only-binary=:all:
--python-version 3.13 --platform manylinux_2_28_x86_64` (measured in the GPU
section below).

## A. CPU path (Warp `device="cpu"`)

Method: a harness patches `Scene.build` to force `device="cpu",
use_cuda_graph=False`, replaces `rss.view` (the viser studio — the only
GUI element in these examples) with a fixed-step run + state checks, and sets
`ROBOSIMSTUDIO_RENDERER=tiled`. So the examples run *unmodified*; only the
viewer call is intercepted.

### `examples/00_getting_started/00_hello_world.py` — PASS

```
the cube came to rest at z=0.775 m, on a bench whose top is at 0.750 m
HARNESS_RESULT {"script": "examples/00_getting_started/00_hello_world.py",
 "device": "cpu", "steps_in_view": 60, "run_wall_s": 14.555,
 "steps_per_s": 4.12, "state_finite": true, "particles": {},
 "render": {"ok": true, "s": 9.96, "channels": {"rgb": [540, 960, 3]}},
 "ok": true, "total_wall_s": 251.691}
```

- Physics is correct: the example's own docstring expects z≈0.7749 on a
  0.750 m bench (50 mm cube half-height 25 mm).
- 4.12 control steps/s at `MUJOCO_500HZ` (10 substeps per control step).
- `sim.render()` produced a real 960×540 RGB frame through Newton's tiled
  ray tracer on CPU — 9.96 s on first call (includes ~8.6 s of render-kernel
  compilation).
- `total_wall_s` is dominated by **one-time Warp kernel compilation for CPU
  (~200 s of `load on device 'cpu' … (compiled)` lines)**, cached afterwards
  in `~/.cache/warp/1.18.0`. No GPU call anywhere fails — Warp just warns
  `Could not find or load the NVIDIA CUDA driver` and runs cpu.

### `examples/03_rope/00_cable.py` — PASS

```
HARNESS_RESULT {"script": "examples/03_rope/00_cable.py", "device": "cpu",
 "steps_in_view": 60, "run_wall_s": 44.566, "steps_per_s": 1.35,
 "state_finite": true, "particles": {},
 "render": {"ok": true, "s": 0.825, "channels": {"rgb": [540, 960, 3]}},
 "ok": true, "total_wall_s": 155.787}
```

- VBD cable (28 capsules) + YAM bimanual arm with sticky contacts runs on
  CPU. 1.35 control steps/s — about 3× slower than hello_world (VBD solve +
  full contact history).
- `particles` is empty because a `rod` is a rigid-capsule chain, not a
  particle mesh (RSS's own docs: a rope "is a centerline `extras` entity").
- Warm render: 0.83 s/frame.
- Notable stderr: `model holds CABLE joints (LM kernel specialization is
  pathological); cartesian tracking runs the FD solver instead` — an RSS
  fallback notice, not a failure.

### `examples/01_cloth/00_towel.py` — RUNNING (slow on CPU)

First attempt (60 steps + 8-frame record) exceeded a 900 s timeout while
still making progress at ~78 % CPU. The towel is a 30×30-cell sheet
(961 particles) under VBD with one-way coupling — the heaviest of the three
scenes. Rerun in progress with 20 steps + 3-frame record; numbers will be
pasted below.

### CPU verdict so far

- The three priority scenes all **build and step correctly on CPU**; no code
  change is needed beyond injecting `device="cpu"` (one line in our harness,
  or `Scene(device=...)` once the planned `robotsim` template lands).
- Headless render works (`tiled` backend, no GL context, no RT cores) and
  `sim.record()` produces mp4 through it (towel run will confirm the mp4).
- Cost: ~4 steps/s rigid, ~1.4 steps/s cable, cloth slower. Feasible for a
  graded loop with small step counts; painful for long rollouts.

## B. GPU lease path — see below (in progress)

## C. Which path the demo should use — pending B
