# Genesis multiphysics — granular column collapse on CPU

A disposable agent-next sandbox installs a pinned, sha256-checked
[Genesis](https://github.com/Genesis-Embodied-AI/genesis-world) 1.4.3
(`genesis-world` on PyPI, Apache-2.0) — the ~30k-star generative
multiphysics engine — and runs a classic MPM granular-column collapse
entirely on the **CPU backend**: a box of elasto-plastic sand particles
(von Mises yield) free-falls onto a rigid peg standing on the floor,
wraps it, and settles into a heap. A judge it cannot fool decides
correctness *from the simulator state* (never pixels): the free-fall
centre of mass is fitted against the ballistic solution `g·t²/2`, mass
and non-penetration are checked particle-by-particle, the final heap's
spread radius and settle speed must land in a physics band, and two runs
at the same seed must be **bit-identical**. A sandbox helps because the
toolchain is ~1 GB of pinned wheels (Taichi-compiled kernels, torch CPU)
that you can install, run and throw away without touching your own
machine.

The artifact under test is a single `SCENARIO` dict in a Python file —
the judge builds the Genesis scene itself, so a scenario cannot pass by
shipping cached positions. Gates and numeric pass rules are in
[SPEC.md](SPEC.md); measured results and real command output are in
[RECEIPT.md](RECEIPT.md).

## Results

Rendered frames from the judged run (Genesis headless rasterizer, real
simulator output — see `media/MANIFEST.json` for provenance):

| t = 0 s (free fall begins) | t = 0.4 s (impact on the peg) | t = 1.2 s (settled heap) |
|---|---|---|
| ![frame 0](media/frame_t0.png) | ![frame 1](media/frame_t1.png) | ![frame 2](media/frame_t2.png) |

## Ask your agent

> Create a CPU sandbox. In it, clone https://github.com/agent-next/sandbox
> and run `bash cookbook/genesis-multiphysics/judge/setup.sh` to install
> the pinned Genesis toolchain. Then write a scenario file (a Python file
> defining one `SCENARIO` dict — see `cookbook/genesis-multiphysics/SPEC.md`
> for the keys and ranges) that simulates a sand column collapsing onto a
> rigid peg on Genesis's CPU backend, and iterate with
> `bash cookbook/genesis-multiphysics/judge/grade.sh <your-scenario.py>`
> until every gate passes. Report the final verdict JSON and kill the
> sandbox when done.

## One-command run (with sandbox API)

```bash
export SBX_API_KEY=<your key>
pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"
python3 cookbook/genesis-multiphysics/run.py      # add --ref <branch> or --keep
```

`run.py` creates a sandbox, clones this repo at `--ref` (default `main`),
runs `judge/setup.sh`, `judge/selftest.sh`, then grades
`examples/good/scenario.py`, prints the verdict JSON, and kills the
sandbox (verifying it is gone) unless `--keep` is given.

## In-sandbox / no API key (run directly inside any Debian 12 box)

```bash
cd cookbook/genesis-multiphysics

# 1. Install the pinned Genesis toolchain (~1 GB of hashed wheels,
#    needs passwordless sudo for the headless-GL apt packages)
bash judge/setup.sh

# 2. Self-test: proves the judge can fail (2 good grades + 6 mutants)
bash judge/selftest.sh

# 3. Grade the known-good scenario (seed 42 for reproducibility)
bash judge/grade.sh examples/good/scenario.py --json /tmp/verdict.json --seed 42
```

### `judge/grade.sh` flags

| flag | purpose | example |
|---|---|---|
| `--json FILE` | write the verdict JSON to `FILE` | `--json /tmp/v.json` |
| `--seed N` | seed passed to `gs.init` (overrides the scenario's) | `--seed 42` |
| `--save-frames DIR` | render 6 headless frames of run 1 into `DIR` (never a gate) | `--save-frames /tmp/fr` |

### Prerequisites

- **Debian 12 (bookworm)**, Python 3.12 — the locked requirements file is
  for the interpreter the agent-next sandbox image ships.
- **passwordless `sudo`** — `judge/setup.sh` apt-installs the Mesa EGL
  libraries the headless rasterizer needs.
- 2 vCPU / ~4 GB RAM is enough; everything is CPU-only.

## Measured wall times (2 vCPU, Debian bookworm)

| step | wall time |
|---|---|
| `judge/setup.sh` (cold) | ~7 min (≈1 GB of hashed wheels) |
| `judge/grade.sh examples/good/scenario.py` | ~8 min (two 1200-step sims; first run includes the one-time Taichi kernel compile) |
| `judge/selftest.sh` | ~35 min (2 good + 6 mutants; three mutants die instantly in spec validation) |

## How the judge decides

Six gates, all numeric (see SPEC.md for exact bands): (1) completes, no
NaN, bounded speed; (2) particle count conserved and every particle
inside the domain at every sample; (3) a least-squares fit of the free-fall
centre of mass recovers the scenario's `g` within 2 %; (4) no particle
penetrates the floor or peg beyond 1.5 particle pitches; (5) the final
heap's 95 %-spread radius lands in `[1.4, 6.0]` half-widths and the
material is settled and collapsed; (6) two runs at the same seed are
bit-identical. `judge/` is sha256-checksummed before and after every
grade.

## Sources

- Genesis: <https://github.com/Genesis-Embodied-AI/genesis-world>,
  `genesis-world` 1.4.3 on PyPI, Apache-2.0. The scene constants in
  `examples/good/scenario.py` were written for this demo.
- The granular-column-collapse gate band is justified against Lajeunesse
  et al. 2005 (*Phys. Fluids* 17, 103302) in SPEC.md's acceptance oracle.

## Limits

- CPU backend only — no GPU, no robotics, one MPM material + rigid bodies.
- Gate 5's spread band reflects this geometry/material; a different
  column aspect ratio needs a different band.
- Taichi kernel compile makes the *first* run in a fresh sandbox slower
  (~7 min build once; ~1 min afterwards, cached in the sandbox only).
