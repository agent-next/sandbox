# Rigid-body drop test with PhysX (USD + ovphysx, headless CPU)

A disposable agent-next sandbox installs a pinned, sha256-checked PhysX
toolchain (the `ovphysx` headless CPU wheel, NVIDIA Omniverse PhysX 6) and
steps one USD rigid-body scene (`scene.usda`) for 10 simulated seconds: a
0.2 m box (4 kg) dropped from 0.80 m and a 0.1 m-radius ball (1 kg)
dropped from 1.20 m onto a static ground, under gravity 9.81 m/s² with
restitution 0.50. A judge it cannot fool decides correctness against an
**independent analytic oracle** — nothing in the judge asks PhysX whether
PhysX is right: free fall must track y₀ − g t²/2, first contact must land
within 1 frame of √(2Δh/g), the resting height must be the geometric
half-extent/radius within 1 mm, the ball's first bounce apex within 10 %
of e²·h, and mechanical energy must never increase. Gates and tolerances
are in [SPEC.md](SPEC.md); measured results and real command output are in
[RECEIPT.md](RECEIPT.md).

A sandbox helps because the toolchain is a 139 MB manylinux wheel plus
~500 MB of installed dependencies that no one wants on a workstation; a
2 vCPU disposable sandbox steps the whole 10 s scene in ~20 s and is gone
afterwards.

The artifact under test is **one file**: a USD ASCII stage
(`examples/good/scene.usda` is the known-good reference, written for this
demo against SPEC.md). The judge copies it to scratch, populates it with
`ovstage`, steps it with single-threaded PhysX in its own `python -I`
process, and never lets the artifact touch the judge: every judged number
is re-derived from the simulator's output files and the scratch copy
itself (gate G7 re-reads the scene text, so animated or scaffolded scenes
fail by name), and `judge/` is sha256-checksummed before and after every
grade.

## The test, in numbers

| gate | rule | known-good value |
|---|---|---|
| G2 free fall | ≤ 1 % of y₀ − g t²/2 pre-contact | rel residual 0.0, ĝ = 9.81 |
| G3 contact time | ≤ 1 frame (4.17 ms) of √(2Δh/g) | Δt = 0.65 frames (both bodies) |
| G4 resting height | within 1 mm of 0.10 m | 0.000 mm (both) |
| G5 bounce apex (ball) | within 10 % of 0.375 m | 0.3733 m (0.43 %) |
| G6 energy | no step gain > 0.5 % E₀; E_final ≤ E₀ | max gain 0.07 % E₀ |
| G7 contract | self-contained dynamic scene, no cheats | 0 violations |

Self-test kills **10/10** single-edit mutant scenes — 7 physics mistakes
(gravity flip, mass 0, missing RigidBodyAPI, missing ground collision,
spawn inside ground, restitution > 1, centimetre units) plus 3 cheat
attempts that **pass every physics gate** and are caught only by the
artifact-contract gate G7 (kinematic animation, a joint scaffold, a hidden
external reference). A mutant killed by crashing the simulator does not
count: the kill rate counts mutants a **gate** fails (rule: ≥ 90 %).

## Ask your agent

> Create a CPU sandbox. In it, clone https://github.com/agent-next/sandbox
> and run `bash cookbook/physx-drop-test/judge/setup.sh` to install the
> pinned PhysX toolchain. Then author a USD ASCII scene (`scene.usda`)
> against `cookbook/physx-drop-test/SPEC.md`: a static ground with its top
> at y = 0, a 0.2 m box of 4 kg dropped from 0.80 m and a 0.1 m-radius
> ball of 1 kg dropped from 1.20 m, gravity (0, −9.81, 0), friction
> 0.60/0.40, restitution 0.50, everything at rest. Iterate with
> `bash cookbook/physx-drop-test/judge/grade.sh <your-scene>.usda --json /tmp/v.json`
> until every gate passes. Report the final verdict JSON and kill the
> sandbox when done.

## One-command run (with sandbox API)

```bash
export SBX_API_KEY=<your key>
pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"
python3 cookbook/physx-drop-test/run.py          # add --ref <branch> or --keep
```

`run.py` (Python 3.10+, stdlib only) creates a sandbox, clones this repo
at `--ref` (default `main`), runs `judge/setup.sh` and
`judge/selftest.sh`, grades the known-good scene, prints the verdict JSON,
and always kills the sandbox — confirming via `sbx list` that the id is
gone (a lost kill reply is not a confirmation) — unless `--keep` is given.
Non-zero exit on any failure, naming the sandbox id.

## In-sandbox / no API key (run directly inside any Linux x86_64 box)

If you already have a Linux x86_64 environment with 2 vCPU, ~4 GB RAM and
**AVX** (the pinned `ovphysx` wheel requires it) — or you are inside the
sandbox created by another tool — you can run the judge steps directly:

```bash
# 1. Install the pinned toolchain into $HOME/.venvs/physx-drop-test
#    (sha256-verified wheels; needs only python3 + venv — no sudo).
#    Set PHYSX_DROP_TEST_VENV=/path/to/venv to install somewhere else.
bash judge/setup.sh

# 2. Self-test: proves the judge can fail (good scene + 10 mutants)
bash judge/selftest.sh

# 3. Grade the known-good scene
bash judge/grade.sh examples/good/scene.usda --json /tmp/verdict.json
```

### `judge/grade.sh` flags

| flag | purpose | example |
|---|---|---|
| `--json FILE` | write verdict JSON to `FILE` | `--json /tmp/v.json` |
| `--seed N` | recorded in verdict JSON (nothing samples it: fixed 2400 steps, single-threaded PhysX) | `--seed 42` |

The judge is deterministic: two runs with the same seed give byte-identical
verdict JSON except the `timing` key (`selftest.sh` checks this). The
verdict JSON written via `--json` additionally carries `seed` and
`timing.wall_seconds` keys, which the stdout print omits.

## Toolchain (pinned, sha256-checked via `pip install --require-hashes`)

- `ovphysx` 0.6.3 (PyPI, manylinux x86_64, 2026-09-16) — NVIDIA Omniverse
  PhysX headless CPU SDK; https://github.com/NVIDIA-Omniverse/PhysX
  (BSD-3-Clause). The newest wheel (0.6.4.72118723, 2026-10-09) was too
  new to pin (released < 2 weeks before pinning).
- `ovstage` 0.2.0.377349 — the `ovphysx` 0.6.3 dependency wheel (same
  licence family), pinned exactly.
- `newton-usd-schemas` 0.5.0 (PyPI, Apache-2.0;
  https://github.com/newton-physics/newton-usd-schemas) — USD schema
  definitions; only its `generatedSchema.usda` directory is read.
- `warp-lang` 1.17.0, `numpy` 2.2.6, `packaging` 23.2 — transitive
  dependencies, sha256-pinned in `judge/requirements.txt`.
- What `setup.sh` actually installed: [`judge/VERSIONS.txt`](judge/VERSIONS.txt)
  (regenerate with `bash judge/versions.sh`).

Example scene, mutants, judge and oracle were written for this repository
(no third-party scene assets).

## Measured wall times (2 vCPU, ~4 GB RAM, Linux x86_64)

All times are measured and pasted in
[RECEIPT.md](RECEIPT.md) (two from-nothing installs, runs A and C; the
first run on a box is faster when pip's wheel cache is warm):

| step | wall time |
|---|---|
| `judge/setup.sh` (cold, ~390 MB download) | ~2 min |
| `judge/setup.sh` (warm pip cache) | ~30 s |
| `judge/setup.sh` (venv already installed) | ~1 s |
| `judge/grade.sh` (one scene, grade.sh wall clock) | ~5–22 s |
| `judge/selftest.sh` (good ×2 + 10 mutants + determinism check) | ~1–4 min |

## Media (see the result without running anything)

- [`media/result.png`](media/result.png) — 3D hero render of the exact
  graded trajectory (both bodies at the measured first-contact moment)
  with the judge's pass lines overlaid, above the three measured panels
  (free fall vs y₀ − g t²/2, bounce apex vs analytic, energy vs E₀).
- [`media/loop.png`](media/loop.png) — the agent loop: gates passed per
  authoring iteration, and the mutant × gate kill matrix (10/10).
- [`media/demo.mp4`](media/demo.mp4) — 42 s, 1920×1080: the drop, the
  bounce, a sped-up real `selftest.sh` run, the verdict and the kill
  matrix ([STORYBOARD.md](media/STORYBOARD.md); machine-gated with
  `cookbook/tools/video_gate.py`, blind-judged in
  [media/REVIEW.json](media/REVIEW.json)).
- [`media/make_media.sh`](media/make_media.sh) regenerates every media
  file from fresh judge runs; [`media/MANIFEST.json`](media/MANIFEST.json)
  records what each file shows, its command, source data and sha256.

The renderer is a deterministic software 3D renderer (perspective
projection, Lambert shading) written for this demo: the pinned `ovphysx`
wheel ships no renderer, so the video and hero render the simulator's own
per-step samples (`traj.npz`, sha256-recorded in the MANIFEST) rather than
a plot of them.

## Reproducibility

- [`REPRODUCE.md`](REPRODUCE.md) — an independent agent (different model
  family from the builder) followed only this README in a fresh venv and
  recorded its numbers; they match [RECEIPT.md](RECEIPT.md) within the
  SPEC tolerances.
- Time-to-result for a cold-start agent following this README: measured in
  RECEIPT.md (~4.5 min to the hero verdict on 2 vCPU CPU).

## Limits

- Headless CPU rigid bodies only: no rendering inside the judge (the
  pinned `ovphysx` wheel is simulation-only and exposes no renderer;
  `media/demo.mp4` renders the judged trajectory headlessly instead),
  no GPU, articulations, deformables or CCD; positions and velocities
  only (no contact forces).
- Gates pin the SPEC.md geometry and materials — a scene solving a
  different drop fails even if physically self-consistent. The contract
  gate (G7) additionally requires the artifact to be one self-contained
  dynamic file: kinematic flags, joints, composition arcs and authored
  velocities are rejected by name.
- The bounce gate assumes a single dominant first rebound; scenes with
  chaotic multi-body contact are out of scope (G6 energy still applies).
- The pinned wheel needs Linux x86_64 with AVX; `setup.sh` exits 2 with a
  clear message on anything else.
