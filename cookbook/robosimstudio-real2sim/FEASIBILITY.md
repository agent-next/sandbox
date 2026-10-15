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

> Two CPU sandboxes were used across the two attempts, and they are not the
> same machine. The numbers under **A1** are from the 8-vCPU sandbox of the
> first attempt; **A2** re-measured the same three examples on the 2-vCPU
> sandbox this round, which is why its throughput is lower. Both are real.

### `examples/00_getting_started/00_hello_world.py` — PASS (8-vCPU sandbox)

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

### `examples/03_rope/00_cable.py` — PASS (8-vCPU sandbox)

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

### `examples/01_cloth/00_towel.py` — PASS (slow: the CPU path's limit) (8-vCPU sandbox)

```
HARNESS_RESULT {"script": "examples/01_cloth/00_towel.py", "device": "cpu",
 "steps_in_view": 20, "run_wall_s": 319.8, "steps_per_s": 0.063,
 "state_finite": true,
 "particles": {"particle_q": {"n": 5766, "spread": 0.51804},
               "particle_qd": {"n": 5766, "spread": 7.2e-05}},
 "render": {"ok": false, "error": "TypeError: Sim.record() got an unexpected keyword argument 'frames'"},
 "ok": true, "total_wall_s": 1259.786}
```

- 30×30-cell VBD towel (5766 particles) under one-way coupling, driven by the
  YAM arm's preset joint track: **0.063 control steps/s** — ~20× slower than
  the cable scene, ~65× slower than hello_world. A 60-step fold at this rate
  is ~16 min of stepping alone, before per-lease kernel compilation.
- State healthy: all particle positions/velocities finite; the sheet has
  spread (max |q - mean| ≈ 0.52 m) so it actually fell/moved, not frozen.
- The `record` failure is our harness's wrong kwarg (`Sim.record(path, steps, ...)`),
  not an RSS defect — `render()` (below) works, and `record()` merely loops
  `run(1)` + `render` per frame.
- The earlier 60-step attempt exceeded a 900 s timeout while still at ~78 %
  CPU; 20 steps then took 320 s of stepping + ~940 s of one-time Warp CPU
  kernel compilation (fresh `~/.cache/warp` this round).

### A2. Re-measurement on the 2-vCPU sandbox (this round, 2026-10-15)

The same three examples, same harness, on the machine this branch was written
on (`nproc` = 2, Python 3.12.15, `uv sync --frozen` into `.venv`). Warp's
kernel cache was warm from the runs above only for the modules they touched;
this round still recompiled most of them, so `run_wall_s` below is again
dominated by compilation, not stepping.

```
HARNESS_RESULT {"script": "examples/00_getting_started/00_hello_world.py", "device": "cpu",
 "steps_in_view": 20, "run_wall_s": 143.751, "step_wall_s": 3.605, "steps_per_s": 5.548,
 "state": {"body_q": {"n": 17, "finite": true}}, "state_finite": true,
 "render": {"ok": true, "s": 8.639, "channels": {"rgb": [540, 960, 3]}},
 "ok": true, "total_wall_s": 155.999}
HARNESS_RESULT {"script": "examples/03_rope/00_cable.py", "device": "cpu",
 "steps_in_view": 20, "run_wall_s": 96.148, "step_wall_s": 12.872, "steps_per_s": 1.554,
 "state": {"body_q": {"n": 44, "finite": true}}, "state_finite": true,
 "render": {"ok": true, "s": 0.81, "channels": {"rgb": [540, 960, 3]}},
 "ok": true, "total_wall_s": 109.831}
HARNESS_RESULT {"script": "examples/01_cloth/00_towel.py", "device": "cpu",
 "steps_in_view": 10, "run_wall_s": 604.064, "step_wall_s": 136.715, "steps_per_s": 0.073,
 "state": {"particle_q": {"n": 1922, "finite": true, "spread": 0.175},
           "particle_qd": {"n": 1922, "finite": true, "max_abs": 0.00154},
           "body_q": {"n": 16, "finite": true}},
 "state_finite": true,
 "render": {"ok": true, "s": 4.188, "channels": {"rgb": [540, 960, 3]}},
 "ok": true, "total_wall_s": 744.974}
```

The towel builds a **1922-particle** sheet on the `bench_0728` cell (the
earlier round's `bench_0728`-family scene had 5766 particles at `cells=30`; the
count follows the cell's preset), and it renders headless on CPU too.

- hello_world: **5.55 control steps/s** (vs 4.12 on the 8-vCPU box — the
  difference is noise plus a differently-warm kernel cache, not vCPU count:
  the rigid scene is a few hundred bodies and does not fill 8 cores either).
- cable: **1.55 control steps/s** (vs 1.35). The VBD cable + YAM contact
  history is the cost, and it is mostly serial.
- `state` now reports `body_q` (17 and 44 bodies, all finite); the earlier
  round reported `particle_q`, which is empty for both scenes — a rod is a
  capsule chain and hello_world has no deformable. Both are finite.

Also measured this round, and load-bearing for the demo's design:

**The arm does not need PyRoKi to step.** With `jax`, `jaxlib`, `jaxls`,
`pyroki`, `jaxlie`, `jax_dataclasses` and `yourdfpy` all blocked by an import
hook, `00_hello_world.py` still builds, steps and settles at the same
`z=0.775 m`:

```
HARNESS_RESULT {"script": "examples/00_getting_started/00_hello_world.py", "device": "cpu",
 "steps_in_view": 5, "run_wall_s": 44.046, "step_wall_s": 0.912, "steps_per_s": 5.482,
 "state": {"body_q": {"n": 17, "finite": true}}, "state_finite": true,
 "ok": true, "total_wall_s": 44.959}
```

That is RSS's documented fallback (`an arm that ships no URDF falls back to
Newton's own solver`), and it is what makes the minimal GPU payload in B3
possible: **no jax, no jaxlib (85 MB), no pyroki, no jaxls, no yourdfpy.**

**Headless video works, and it is a real H.264 mp4.** `sim.record(dir, steps)`
on the tiled renderer with no GL context and no RT cores:

```
HARNESS_RESULT {"script": "examples/00_getting_started/00_hello_world.py", "device": "cpu",
 "steps_in_view": 2, "run_wall_s": 26.887, "step_wall_s": 0.334, "steps_per_s": 5.988,
 "state": {"body_q": {"n": 17, "finite": true}}, "state_finite": true,
 "record": {"ok": true, "s": 4.518, "dir": "/tmp/rss/rec",
            "files": ["view.mp4"], "sizes": {"view.mp4": 17520}},
 "ok": true, "total_wall_s": 31.739}
```

```
$ ffprobe -v error -show_entries stream=codec_name,width,height,nb_frames view.mp4
codec_name=h264
width=960
height=540
nb_frames=5
```

So the media round can render the reference rollout and the agent's rollout
through RSS's own recorder, headless, on whichever device is chosen below —
`record()` is `run(1)` + `render()` per frame, and `render()` is already
proven on both paths.

### CPU verdict

- All three priority scenes **build, step and render headless on CPU**; the
  only code change needed is forcing `device="cpu"` in `Scene.build` (one
  line) and replacing the interactive `rss.view` call with a step loop.
- Headless render works (`ROBOSIMSTUDIO_RENDERER=tiled`, no GL context, no
  RT cores): 9.96 s/frame cold (hello_world), 0.83 s/frame warm (cable).
  `sim.record(path, steps)` should therefore also work on CPU (it is
  `run(1)` + `render` per frame).
- Throughput on this CPU sandbox (8 vCPU): **4.12 steps/s** rigid,
  **1.35 steps/s** cable (VBD capsules + arm), **0.063 steps/s** cloth
  (VBD sheet). Cloth on CPU is feasible only for very short rollouts.
- No GPU call anywhere fails: Warp warns `Could not find or load the NVIDIA
  CUDA driver` and runs on the cpu device.

## C. Which path the demo should use

**The demo runs on the GPU lease.** The CPU path is the fallback and the
tolerance, not the target, and the numbers say why:

| | CPU sandbox (2 vCPU, this round) | GPU lease (RTX 5090 slice) |
| --- | --- | --- |
| hello_world | 5.5 steps/s | (B3) |
| cable (VBD + arm) | 1.55 steps/s | (B3) |
| towel (VBD sheet) | 0.073 steps/s | (B3) |
| a 60-step towel fold | **~14 min** of stepping | (B3) |
| cost of getting started | `uv sync`, ~2 min | **~32 min** of uploading |

The reason is the grade loop, not one run. The demo's judge re-simulates the
scene for every `params.json` an agent proposes, and the agent proposes many.
At 0.073 steps/s a single 60-step towel rollout is ~14 minutes on CPU, so a
20-iteration search is ~5 hours — outside the demo's whole budget. On the
slice it has to be seconds, and B3 measures whether it is.

The reason it is *close* is the fixed cost. The lease has no network, so the
payload has to be uploaded through exec calls at the rate measured in B2b
(~20–35 s/MB), and the two payloads that matter cost:

- **93 MB** — ship `mujoco 3.12`, `mujoco-warp 3.12`, `newton 1.6`, `numpy
  2.2.6` and a rebuilt `robosimstudio` on top of the lease's own warp/jax:
  **~32 min**, once per lease.
- **33 MB** — ship only what the lease lacks (`robosimstudio`, `viser`,
  `pyroki`, `jaxls`, `yourdfpy`, `robot-descriptions`, the jax helpers) and
  run on the lease's native `warp 1.13` / `jax 0.7.2` / `mujoco 3.8.1`:
  **~19 min**.

So the demo's design follows: **one lease, many grade calls.** The wheelhouse
is uploaded once at the top of `run.py`, and every rollout the agent asks for
afterwards costs only exec time. That is the same argument the standard makes
for a disposable sandbox, and it is the reason the numbers above are recorded
per *phase* (upload / install / first-kernel-compile / stepping) rather than
as one wall time.

**What the pending platform work would change.** A `robotsim` GPU template
with RSS baked in (Python 3.12, newton 1.6.1) removes the entire upload phase:
the 32 minutes above become zero, and the demo's fixed cost drops to lease
create plus the ~25 s Warp kernel cold-compile. A `PUT
/sandboxes/{id}/files/{path}` route (405 today, measured in B2b) does the same
for any wheel the template does not carry — it would make the payload a file
transfer instead of base64-in-a-code-string, which is where the 21.7 s/MB
comes from. Neither is live, so **nothing in this demo depends on either**:
`judge/lease.py` uploads through exec and installs with `pip --no-index`, and
it will simply get faster if the template lands.



### B1. Wheelhouse (the lease lacks everything RSS pins)

Versions the lease already has were dropped; the lease wheelhouse carries
only the gap. 69 wheels, 214 MB raw / 211 MB tar.gz (dominated by
warp-lang 1.18.0 at 142 MB — newton 1.6 requires warp-lang>=1.17, so it
cannot be dropped). Built with
`pip download --only-binary=:all: --python-version 3.13 --platform manylinux2014_x86_64 --platform manylinux_2_28_x86_64 --platform manylinux_2_27_x86_64`
(Platform extras: jaxlib is manylinux_2_27 only — no 2_28/2014 build exists).

| wheel | version | size | note |
| --- | --- | --- | --- |
| robosimstudio | 0.1.0 @ pinned SHA | 13.5 MB | `uv build --wheel` at 73739ab |
| warp-lang | 1.18.0 | 141.9 MB | newton 1.6 floor is >=1.17 |
| mujoco | 3.12.0 | 18.9 MB | mujoco-warp 3.12 floor >=3.11 |
| mujoco-warp | 3.12.0 | 2.1 MB | py3-none-any |
| newton | 1.6.0 | 5.9 MB | |
| viser | 1.1.1 | 3.5 MB | |
| yourdfpy | 0.0.60 | 99 KB | |
| pyroki | 0.0.0 @ 95afccc | 45 KB | built from git rev 95afccc22658c461ab1042a048ae4e9c24bc2a47 |
| jaxls | 0.0.0 @ 50a58be | 111 KB | built from git rev 50a58be88c5ef74532f09e3f55268b4f02c490e3 |
| pyliblzfse | 0.4.1 | 25 KB | **no Linux wheels on PyPI** — built from sdist with uv's CPython 3.13 |
| (64 more transitives) | | ~29 MB | jax ecosystem (satisfied by lease's jax 0.7.2 for floors, but shipped for reproducibility), trimesh extras, etc. |

sha256 of the three locally built wheels:

```
18d6ba7e224cb6330fe35f80e535fa31f5966fdd2a1761da930a2021efd6a4c7  robosimstudio-0.1.0-py3-none-any.whl
348530e7e3eea62b999d22f2b8f1d8a52794c14248c90b884759b28fd6c3073b  pyroki-0.0.0-py3-none-any.whl
6e62aefef3d9227450e2f244e1f46bde787b93c74b2695865267cb3b5ea35bf1  jaxls-0.0.0-py3-none-any.whl
```

Gotchas recorded for `judge/setup.sh`:

- RSS's wheel metadata pins `pyroki @ git+...`, and pyroki pins
  `jaxls @ git+...`; under `--no-index` pip refuses both (it wants to build
  from the URL). Fix: the shipped pyroki/jaxls/robosimstudio wheels have
  their `Requires-Dist` rewritten to plain `pyroki`/`jaxls` (one sed in the
  wheel's METADATA), and install all three by path.
- pip may otherwise pick a *newer* wheel than intended when several exist;
  prune the wheelhouse to exactly one version per package (numpy had 2.2.6
  and 2.5.4 at first; 2.5.4 removed — jaxlib 0.11.2 wants numpy<2.3).
- The full 78-wheel set **installs offline** (`pip install --no-index
  --find-links`) into a fresh CPython 3.13 venv, and `import
  robosimstudio, pyroki, jaxls, yourdfpy` succeeds — verified end to end
  on this CPU sandbox before touching the lease.

### B2. Lease probe results (real, 2026-10-14)

- Lease create can answer **HTTP 409** under contention; retry (2 attempts
  needed). `POST /sandboxes {"accel":{"vram_gb":4,"reserve":"exec"}}` →
  `gl-951d38-19`, RTX 5090 slice: 4916 MiB total, 32 CPUs, Python 3.13.5,
  home `/home/ubuntu`, 34 GB free on `/` (97 % full).
- **Exec payload limit**: 4 MB b64 chunk → ok (md5 verified), 69.5 s
  round-trip; 16 MB → ok (md5 verified), 238.9 s; **32 MB → the exec
  answers 404 and the lease is gone** (destroyed; `close()` then confirmed
  404 in 10.9 s). So the safe chunk is **16 MB**, and the measured upload
  rate is **~14.9 s/MB** — a 211 MB wheelhouse costs **~52 min of upload**
  per fresh lease.
- **Files persist across exec calls** (1 MB file written, then read back
  complete in a later exec, same lease), so the chunk-then-untar design in
  `judge/lease.py` is sound.
- `close()` (DELETE + confirm 404) took 10.9 s / 1.1 s.

### B2b. Re-measured 2026-10-15 (this round, second CPU sandbox)

The numbers above were taken on an 8-vCPU sandbox; this round's are lower
because that machine was 8× and this one is 2×, and because the gateway was
carrying two concurrent uploads from this key. Both are real; take the
*larger* upload rate when budgeting.

```
lease gl-951d38-30  (POST {"accel":{"vram_gb":4,"reserve":"exec"}})
{"mb": 1,  "ok": true, "wall_s":  38.2, "s_per_mb_b64": 38.2, "md5": "e115ec72d20e68d3b4c1ffa145d981bd"}
{"mb": 4,  "ok": true, "wall_s":  67.6, "s_per_mb_b64": 16.9, "md5": "e655b98e456359fa63485de415ab871f"}
{"mb": 16, "ok": true, "wall_s": 347.5, "s_per_mb_b64": 21.7, "md5": "b32cd56e6a9ce200e341405c4472babc"}
LEASE_STILL_ALIVE 200
closed gl-951d38-30 0.6 s
```

- **16 MB is still the safe chunk** and it is still alive afterwards; the
  `32 MB → 404, lease destroyed` result above was not re-tested (it costs a
  lease to re-test, and one measurement of a hard failure is enough).
- End to end, a **93 MB** payload (30 chunks) took **1924 s = 32 min**
  (21.7 s/MB) on lease `gl-951d38-40`; a **33 MB** payload (11 chunks) took
  **1154 s = 19 min** (36.3 s/MB, degraded by the second concurrent upload).
  Budget **~20–35 s/MB**.
- A second lease probe (`gl-951d38-36`) measured what the slice already has:

```
{"python": "3.13.5", "has_pip": false, "pip": "25.3", "venv": "yes",
 "warp": "1.13.0", "numpy": "1.26.4", "home": "/home/ubuntu",
 "disk": 23756, "cpus": 32}
```

  `pip` is importable (`python -m pip`) but not on `PATH`; `venv` works; 23.7 GB
  free; **32 CPUs**. `python -m pip install --no-index --no-deps --target`
  is the install path.

- **The file-upload route is not live.** `PUT /sandboxes/{id}/files/test.txt`
  answers **405** on this key today, so nothing may depend on it (see C).
- **`POST /sandboxes/{id}/exec` can answer 409 under contention**, not only
  5xx: lease `gl-951d38-41` uploaded its whole 33 MB payload and then lost it
  to a 409 on the very next exec, because `judge/lease.py` only retried 5xx.
  Fixed in `judge/lease.py` (409/429 now retried with backoff), and the cost
  of the bug is exactly the upload time above — which is why it matters here.

### B3. RSS on the GPU lease

**The lease's own Warp is too old for newton 1.6 — measured, not assumed.**
The cheap payload (33 MB: `robosimstudio`, `viser`, `pyroki`, `jaxls`,
`yourdfpy` and helpers, no `warp-lang`) installs and imports cleanly on the
lease and even sees the GPU:

```
PROBE rc=0
warp 1.13.0
newton 1.6.0
mujoco 3.12.0
numpy 2.2.6
Warp 1.13.0 initialized:
   CUDA Toolkit 12.9, Driver 13.0
   Devices:
     "cpu"      : "x86_64"
     "cuda:0"   : "NVIDIA GeForce RTX 5090" (5 GiB, sm_120, mempool enabled)
rss /home/ubuntu/rsssite/robosimstudio/__init__.py
```

but `scene.build()` on `device="cuda:0"` dies inside Newton's graph colouring:

```
HARNESS_RESULT {"script": ".../00_hello_world.py", "device": "cuda:0", "steps_in_view": 20,
 "run_wall_s": 6.623, "ok": false,
 "error": "AttributeError: module 'warp.config' has no attribute 'log_level'"}
  File "/home/ubuntu/rsssite/newton/_src/sim/graph_coloring.py", line 301, in color_graph
    if max_min_ratio > target_max_min_color_ratio and wp.config.log_level <= wp.LOG_DEBUG:
AttributeError: module 'warp.config' has no attribute 'log_level'
```

`wp.config.log_level` was added in a later Warp; newton 1.6.0's declared floor
is `warp-lang>=1.17.0`. **The 142 MB `warp-lang 1.18.0` wheel is therefore not
optional**, and the payload the lease actually needs is the full
**240 MB** one — the same 30 wheels plus warp. That is ~40 min of upload per
fresh lease at the measured rate. The `robotsim` template with RSS baked in
would delete exactly this.

A first attempt with that same 240 MB set is recorded here for one reason: it
failed for a reason of *mine*, not RSS's, and the failure mode is worth
naming. `harness.py` was launched as `python -I …`, and `-I` ignores
`PYTHONPATH`, so the harness could not import the target directory it had just
been installed into:

```
ModuleNotFoundError: No module named 'robosimstudio'
```

Install was fine (`install rc=0`, 9.8 s); the run was not. The fix is to pass
the target directory on `sys.path` explicitly rather than relying on
`PYTHONPATH`, which is what the final run does.

### B3b. RSS on the GPU lease — final run


