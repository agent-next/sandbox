# GPU sim sweep: one world on CPU, thousands on a GPU slice

An agent works on a real GPU-simulation engineering problem inside a disposable
sandbox: configure a MuJoCo-Warp scene (a 7-DoF arm + 8 falling boxes on a
table), sweep it over nworld = 1..8192 on a 4 GiB RTX 5090 slice, verify the
physics at every point against a CPU baseline, and produce a throughput curve
with the speedup over CPU reported honestly. The judge never accepts "it ran":
it re-runs the same physics on CPU, compares trajectories, checks the oracle at
every sweep point, and gates the throughput claim.

A sandbox helps because GPU simulation work is messy: it pins a specific
mujoco/mujoco-warp toolchain without touching your machine, safely runs
untrusted agent-written configs, and gets destroyed afterwards. On a CPU-only
sandbox the judge runs `--cpu-check` (structure gate only); on a GPU sandbox it
runs the full path including the throughput measurement. The GPU path uses a
4 GiB VRAM slice lease created over the REST API (see
`cookbook/small-gpu/run.py`) with `run.py --gpu`.

## One-command run

From this repository's root, with Python 3.10+ and the `sbx` CLI
(`pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"`)
and `SBX_API_KEY` exported:

```bash
python3 cookbook/gpu-sim-sweep/run.py            # CPU sandbox: --cpu-check judge
python3 cookbook/gpu-sim-sweep/run.py --gpu      # GPU lease: full judge
python3 cookbook/gpu-sim-sweep/run.py --ref sbx/demo-gpu-sim-sweep   # other ref
```

Each run prints wall time per step (clone, setup, selftest, grade), the
verdict JSON, and a short human summary, then kills the sandbox/lease and
confirms it is gone. Measured on the CPU path (see RECEIPT.md): clone
seconds, cold setup ~1 min, selftest ~2 min, grade ~10 s. The GPU path
needs GPU access on your key and will take longer (Warp kernels cold-compile
~25 s per fresh lease).

To try the judge locally on a CPU-only Linux box instead:

```bash
bash cookbook/gpu-sim-sweep/judge/setup.sh      # pinned venv in ~/.venvs/gpu-sim-sweep
bash cookbook/gpu-sim-sweep/judge/selftest.sh   # known-good passes, 6/6 mutants killed
bash cookbook/gpu-sim-sweep/judge/grade.sh cookbook/gpu-sim-sweep/examples/good/sweep.json
```

Limits, stated plainly: physics correctness is the gate; throughput is
*reported*, not gated (a `--speedup-floor F` option exists if you want to
gate on it). The CPU judge proves the config is structurally valid; it cannot
measure GPU throughput — that needs the GPU lease. See `SPEC.md` for the
exact gates, `RECEIPT.md` for real measured output.

## GPU path details

The `--gpu` flag creates a 4 GiB VRAM slice lease via the agent-next REST API:
- `POST /sandboxes {"accel":{"vram_gb":4,"reserve":"exec"}}` — creates the lease
- `POST /sandboxes/{id}/exec {"code": <python>, "timeout_s": N}` — runs the grading job
- `DELETE /sandboxes/{id}` + `GET /sandboxes/{id}` → 404/dead — confirms cleanup

The lease image already has Python 3.13, mujoco 3.8.1, mujoco-warp 3.8.1,
warp-lang 1.13.0, numpy 1.26.4 on an RTX 5090 slice (cc 12.0); no pip needed.
The grading job packs `judge/` and `examples/` as a base64 tar.gz, extracts
them on the lease, runs the full judge (structure + CPU reference + GPU sweep
+ oracle), and grades all 6 mutants.

## Media

`media/` regenerates the demo figures and video from committed source
data (`media/data/gpu-run.log`, `media/data/report.json` — the latter
produced by `run.py --gpu --report-json media/data/report.json`):

```bash
bash cookbook/gpu-sim-sweep/media/make_media.sh   # needs ffmpeg; pinned venv
```

It writes `media/result.png`, `media/loop.png`, `media/demo.mp4` and a
`media/MANIFEST.json` with sha256s; see `media/REVIEW.md`.

## Ask your agent

With the sandbox plugin installed, paste this prompt. The agent designs
and fixes the sim config itself in a sandbox and iterates with the judge until
it passes — that loop is the demo:

> Create a fresh sandbox (GPU lease, `vram_gb: 4` if GPU access is on
> my key; otherwise a plain sandbox and the judge's `--cpu-check` mode).
> Inside it, clone https://github.com/agent-next/sandbox at ref `main`,
> then read `cookbook/gpu-sim-sweep/SPEC.md` carefully: you are to implement
> `cookbook/gpu-sim-sweep`'s MuJoCo-Warp sim sweep as a config file,
> `sweep.json`, with the scene XML, physics parameters, nconmax/njmax contact
> capacity, and nworld ladder exactly as the spec's artifact contract says.
> The scene is a 7-DoF arm + 8 boxes falling on a table; the canonical XML is
> in `judge/scene.py`. First run `cookbook/gpu-sim-sweep/judge/setup.sh`, then
> write your config, then iterate: `bash cookbook/gpu-sim-sweep/judge/grade.sh
> /path/to/your/sweep.json --json /tmp/v.json` and read the verdict JSON
> until every gate passes. The judge's self-test shows what it rejects —
> run `judge/selftest.sh` once to see 6 broken mutants die. When every
> gate passes, report the verdict JSON (CPU steps/s, top GPU steps/s,
> speedup, and per-point oracle results), then kill the sandbox and confirm
> it is gone. If you cannot get a gate to pass, say exactly which gate and
> what you tried, and stop.

## What the judge checks (short form)

| gate | rule |
|---|---|
| structure | valid JSON, ≤ 256 KiB, all required keys, scene XML matches canonical |
| engine-parity | GPU mujoco version == CPU mujoco version |
| physics-oracle | every nworld: finite, arm err < 0.15 rad, boxes landed (z in bounds), speed < 5 m/s |
| cpu-parity | GPU world-0 trajectory matches CPU within 1e-3 rad |
| throughput | top nworld steps/s ≥ floor × CPU steps/s (default floor 20x) |

The artifact is graded from a copy in a temp dir, and sha256 checksums of
`judge/` are compared before and after — the artifact cannot tamper with
its own judge.
