# WebGL fluid simulation, customised and graded headless on CPU

A disposable agent-next sandbox installs a pinned, sha256-checked
headless Chromium and runs
[PavelDoGreat/WebGL-Fluid-Simulation](https://github.com/PavelDoGreat/WebGL-Fluid-Simulation)
(~17k GitHub stars, MIT, pinned at commit
`a2d292931f19d9b3b9f564e23e6c32729d2121c3` — see judge/VERSIONS.txt for
the exact SHA) end to end on **CPU WebGL** (SwiftShader — no GPU). The
artifact under test is an agent-written *scene*: a `config.json`
(timestep, splat script, obstacle rectangles) plus `drive.js` (the
deterministic driver) plus `obstacle.frag` (the agent's GLSL patch that
enforces solid obstacles inside the solver). The judge loads the pinned
upstream sim inside its own harness, drives the artifact's declared
script with a fixed `dt` (no wall clock anywhere), reads the dye texture
out of the GPU itself, and grades six physics-ish gates — determinism,
advection direction, obstacle integrity, dissipation law — against the
artifact's own declared intent. See [SPEC.md](SPEC.md) for the numeric
pass rules and [RECEIPT.md](RECEIPT.md) for real run output.

A sandbox helps because the whole toolchain — Chromium + SwiftShader +
pinned upstream sources — is fetched, verified and thrown away inside a
disposable box, and the sim runs identically on a machine with no GPU.

## Results

- The scene runs **84 fixed-dt frames twice** in one headless Chromium;
  every frame's RGBA dye readback is **bit-identical** between runs
  (gate 2, `hash_equal: true`).
- Probe dye centroid advects **0.136** normalized units at **0.02°**
  off the declared probe velocity (gate 3 allows 60°, requires forward
  progress at 6-frame granularity).
- **0.000 %** of dye mass inside either declared obstacle after the aim
  splat (gate 4 allows 0.5 %; the same scene with the mask patch removed
  leaks 17 % — the self-test kills it).
- Stationary patch decays at **0.98482/frame** vs the configured
  `exp(-dt·DENSITY_DISSIPATION)` = 0.98413 (ratio 1.0007, monotone).
- Self-test kills **5/5** known-bad mutants (velocity flip, ignored
  obstacles, dissipation 0, NaN injection, broken shader).

Frame series of the good run are in [media/](media/).

## Ask your agent

> Create a CPU sandbox. In it, clone https://github.com/agent-next/sandbox
> and run `bash cookbook/webgl-fluid/judge/setup.sh` to install the pinned
> headless Chromium toolchain. Then customise the WebGL fluid scene: copy
> `cookbook/webgl-fluid/examples/good/` to a scratch dir, edit
> `config.json`/`drive.js`/`obstacle.frag` — e.g. move the obstacle
> rectangles, change the splat colours and script a different dye
> sequence — and iterate with
> `bash cookbook/webgl-fluid/judge/grade.sh <your-scene-dir>` until every
> gate passes. Report the final verdict JSON and kill the sandbox when
> done.

## One-command run (with sandbox API)

```bash
export SBX_API_KEY=<your key>
pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"
python3 cookbook/webgl-fluid/run.py          # add --ref <branch> or --keep
```

`run.py` creates a sandbox, clones this repo at `--ref` (default
`main`), runs `judge/setup.sh`, `judge/selftest.sh`, then grades
`examples/good`, prints the verdict JSON, and kills the sandbox
(verifying it is gone) unless `--keep` is given.

## In-sandbox / no API key (run directly inside any Debian 12 box)

```bash
# 1. Install the pinned toolchain (needs passwordless sudo for apt libs)
bash judge/setup.sh

# 2. Self-test: proves the judge can fail (2 good grades + 5 mutants)
bash judge/selftest.sh

# 3. Grade the known-good artifact (seed 42 for reproducibility)
bash judge/grade.sh examples/good --json /tmp/verdict.json --seed 42

# Optional: dump real PNG frames of the run for media
bash judge/grade.sh examples/good --keep-frames /tmp/frames --frames "0 34 60 83"
```

### `judge/grade.sh` flags

| flag | purpose | example |
|---|---|---|
| `--json FILE` | write verdict JSON to `FILE` | `--json /tmp/v.json` |
| `--seed N` | recorded in the verdict JSON | `--seed 42` |
| `--keep-frames DIR` | write real PNGs of run-1 frames (dye RGBA readback) | `--keep-frames /tmp/fr` |
| `--frames "i j k"` | which frames `--keep-frames` writes | `--frames "0 40 83"` |

### Prerequisites

- **Debian 12 (bookworm)** or compatible; **passwordless `sudo`** —
  `judge/setup.sh` apt-installs Chromium's runtime libraries.
- 2 vCPU / ~3 GB RAM; nothing needs a GPU (SwiftShader renders on CPU).
- Everything else (Node 20, playwright-core, Chromium build 1187, the
  pinned upstream files) is downloaded with sha256 verification into
  `$HOME/.wfs-fluid` by `judge/setup.sh` — see `judge/VERSIONS.txt`.

## Measured wall times (2 vCPU, Debian bookworm)

| step | wall time |
|---|---|
| `judge/setup.sh` (cold) | ~3–6 min (Chromium download dominates) |
| `judge/grade.sh examples/good` | ~2.5 min |
| `judge/selftest.sh` (2 good + 5 mutants) | ~18 min |

## Upstream credit

[PavelDoGreat/WebGL-Fluid-Simulation](https://github.com/PavelDoGreat/WebGL-Fluid-Simulation),
MIT licence, pinned at commit
`a2d292931f19d9b3b9f564e23e6c32729d2121c3` (2024-11-12). The pinned
files (`script.js`, `dat.gui.min.js`, `LICENSE`, `LDR_LLL1_0.png`) are
sha256-verified by `judge/setup.sh` at install and again by
`judge/grade.sh` at every grade.

## Limits

- Fixed scene only: axis-aligned obstacle rectangles, scripted splats,
  fixed `dt`. No interaction, no real-time loop, no audio.
- WebGL2 + float color buffers via SwiftShader; bloom/sunrays/shading are
  forced off so pixel checks are exact.
- Determinism is bit-level here; if a different grading host proves
  nondeterministic, gate 2 falls back to mean SSIM ≥ 0.99 (the verdict
  records which branch fired — see SPEC.md).
