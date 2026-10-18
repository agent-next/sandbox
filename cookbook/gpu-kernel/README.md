# GPU kernel optimisation loop

An agent works on a real GPU-kernel engineering problem inside a disposable
sandbox: write a fused row-wise **softmax** Triton kernel for fp32 tensors
and iterate against a judge it cannot fool. The judge never accepts "it
ran": it compiles the kernel to real device code (sm_80 + sm_90 cubins),
compares it against torch eager over odd shapes and adversarial
distributions, checks the analytic properties (rows sum to 1, shift
invariance, output in [0, 1]), verifies the input is untouched, and only
then reports speed honestly (median CUDA-event timing vs `torch.softmax`).

A sandbox helps because kernel work is messy: it pins a specific
torch/triton toolchain without touching your machine, safely runs
untrusted agent-written kernels, and gets destroyed afterwards. On a
CPU-only sandbox the judge runs `--cpu-check` (offline device compile +
interpreter numerics); on a GPU sandbox it runs the full path including the
speed measurement. The GPU path uses a 1 GiB VRAM slice lease created over
the REST API (see `cookbook/small-gpu/run.py`) with `run.py --gpu`.

## One-command run

From this repository's root, with Python 3.10+ and the `sbx` CLI
(`pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"`)
and `SBX_API_KEY` exported:

```bash
python3 cookbook/gpu-kernel/run.py            # CPU sandbox: --cpu-check judge
python3 cookbook/gpu-kernel/run.py --gpu      # GPU lease: full CUDA judge
python3 cookbook/gpu-kernel/run.py --ref sbx/demo-gpu-kernel-3   # other ref
```

Each run prints wall time per step (clone, setup, selftest, grade), the
verdict JSON, and a short human summary, then kills the sandbox/lease and
confirms it is gone. Measured on the CPU path (see RECEIPT.md): clone
seconds, cold setup ~1 min, selftest ~2 min, grade ~11 s. The GPU path
needs GPU access on your key and will take longer (the CUDA closure is a
multi-GB download on first setup).

To try the judge locally on a CPU-only Linux box instead:

```bash
bash cookbook/gpu-kernel/judge/setup.sh      # pinned venv in ~/.venvs/gpu-kernel
bash cookbook/gpu-kernel/judge/selftest.sh   # known-good passes, 11/11 mutants killed
bash cookbook/gpu-kernel/judge/grade.sh cookbook/gpu-kernel/examples/good/kernel.py
```

Limits, stated plainly: correctness is the gate; speed is *reported*, not
gated (a `--speed-target T` option exists if you want to gate on it). The
CPU judge proves the kernel compiles to device code and is numerically
right; it cannot measure GPU speed — that needs the GPU lease. See
`SPEC.md` for the exact gates, `RECEIPT.md` for real measured output.

## GPU path details

The `--gpu` flag creates a 1 GiB VRAM slice lease via the agent-next REST API:
- `POST /sandboxes {"accel":{"vram_gb":1,"reserve":"exec"}}` — creates the lease
- `POST /sandboxes/{id}/exec {"code": <python>, "timeout_s": N}` — runs the grading job
- `DELETE /sandboxes/{id}` + `GET /sandboxes/{id}` → 404/dead — confirms cleanup

The 1 GiB slice is a hard cap on the whole vGPU device, not a tensor
budget: expect `vram_gb − 0.7 GiB baseline − ~0.3 GiB per CUDA process` of
allocatable memory (measured 2026-10-15 on gpu-lease-v06), so the grading
job's tensors and Triton workspaces must fit in ~0.3–0.6 GiB.

The lease image already has Python 3.13, torch 2.10.0+cu128, triton 3.6.0, numpy 1.26.4 on an RTX 5090 slice (cc 12.0); no nvcc, no pip needed. The grading job packs `judge/` and `examples/` as a base64 tar.gz, extracts them on the lease, runs the full judge (structure, device-compile for sm_80/sm_90, 10 correctness cases on CUDA, speed measurement on 4096x4096), and grades all 11 mutants.

## Media

`media/` regenerates the demo figures and video from committed source
data (`media/data/gpu-run.log`, `media/data/report.json` — the latter
produced by `run.py --gpu --report-json media/data/report.json`):

```bash
bash cookbook/gpu-kernel/media/make_media.sh   # needs ffmpeg; pinned venv
```

It writes `media/result.png`, `media/loop.png`, `media/demo.mp4` and a
`media/MANIFEST.json` with sha256s; see `media/REVIEW.md`.

## Ask your agent

With the sandbox plugin installed, paste this prompt. The agent designs
and fixes the kernel itself in a sandbox and iterates with the judge until
it passes — that loop is the demo:

> Create a fresh sandbox (GPU lease, `vram_gb: 1` if GPU access is on
> my key; otherwise a plain sandbox and the judge's `--cpu-check` mode).
> Inside it, clone https://github.com/agent-next/sandbox at ref `main`,
> then read `cookbook/gpu-kernel/SPEC.md` carefully: you are to implement
> `cookbook/gpu-kernel`'s fused row-wise softmax as a single Triton kernel
> in one file, `kernel.py`, exposing `softmax(x)`, `KERNEL`, `SIGNATURE`
> and `CONSTEXPRS` exactly as the spec's artifact contract says. Do not
> delegate to torch's own softmax — the judge greps for it and counts
> kernel launches. First run `cookbook/gpu-kernel/judge/setup.sh`, then
> write your kernel, then iterate: `bash cookbook/gpu-kernel/judge/grade.sh
> /path/to/your/kernel.py --json /tmp/v.json` and read the verdict JSON
> until every gate passes. The judge's self-test shows what it rejects —
> run `judge/selftest.sh` once to see 10 broken mutants die. When every
> gate passes, report the verdict JSON (worst max-abs error, row-sum
> error, and — GPU only — kernel vs eager milliseconds and the speedup),
> then kill the sandbox and confirm it is gone. If you cannot get a gate
> to pass, say exactly which gate and what you tried, and stop.

## What the judge checks (short form)

| gate | rule |
|---|---|
| structure | ≤ 64 KiB, byte-compiles, `softmax`/`KERNEL`/`SIGNATURE`/`CONSTEXPRS` present and consistent, no softmax-delegation names |
| device-compile | `triton.compile` of `KERNEL` → cubin for sm_80 **and** sm_90, offline |
| correctness | vs `torch.softmax`: max abs err ≤ 1e-5, `allclose(rtol 1e-5, atol 1e-6)`; rows sum to 1 (≤ 1e-4); finite, in [0, 1]; shift-invariance (x vs x+777) ≤ 1e-5; ≥ 1 kernel launch observed; input bit-identical — over 10 cases incl. (4096,4096), odd cols 4093/65, (3,1), overflow-forcing ×64 inputs, big-offset +5000, last-column max +50, zeros, const |
| speed | reported: median of 9 CUDA-event timings vs torch eager on (4096, 4096); only gates with `--speed-target` |

The artifact is graded from a copy in a temp dir, and sha256 checksums of
`judge/` are compared before and after — the artifact cannot tamper with
its own judge.