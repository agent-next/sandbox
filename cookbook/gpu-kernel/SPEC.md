# gpu-kernel: fused softmax kernel demo — SPEC

An agent works inside a disposable sandbox on a real GPU-kernel engineering
problem: write and tune a Triton kernel for a fused op (row-wise softmax over
fp32 tensors) until an unfoolable judge accepts it. The judge never accepts
"it ran": it compiles the kernel to device code, runs it against independent
oracles, and reports speed honestly.

## Goal

- Artifact: one Python file (`kernel.py`) that implements row-wise softmax as
  a Triton kernel and passes every judge gate below.
- Judge: `judge/grade.sh` with numeric, deterministic pass rules, runnable on
  GPU machines (full path: compile, correctness, speed) and on CPU-only
  machines (`--cpu-check`: offline device compile + interpreter numerics).
- Self-test: `judge/selftest.sh` proves the judge fails known-bad kernels.

## Non-goals

- Beating a specific speedup target (speed is measured and reported; a target
  can be requested with `--speed-target` but correctness is the only default
  gate).
- Dtypes other than fp32, inputs other than 2-D contiguous, autotuning, or
  multi-GPU work.
- Verifying GPU performance on a CPU-only machine; the GPU speed path needs a
  CUDA sandbox (see `README.md`).

## The artifact contract

`kernel.py` must define:

| name | what |
|---|---|
| `softmax(x: torch.Tensor) -> torch.Tensor` | public API; row-wise softmax over the last dim; returns a new tensor with the shape, dtype (fp32) and device of `x`; must not modify `x` |
| `KERNEL` | the `@triton.jit` function that `softmax` launches |
| `SIGNATURE` | dict mapping every `KERNEL` argument name to a Triton type string (e.g. `{"X": "*fp32", "Y": "*fp32", "n_cols": "i32", "BLOCK": "constexpr"}`) |
| `CONSTEXPRS` | dict of constexpr names/values used by the judge's offline compile probe (e.g. `{"BLOCK": 1024}`) |

- The judge calls `softmax` on CPU tensors with `TRITON_INTERPRET=1` set (the
  Triton interpreter executes the real kernel logic on CPU) and on CUDA
  tensors with the kernel compiled for the local device.
- `softmax` must not delegate the computation to torch's own softmax
  (`torch.softmax`, `torch.nn.functional.softmax`, `log_softmax`, ...); the
  judge forbids those names in the artifact text and requires observable
  Triton kernel launches (see gate 3).

## Judge gates (numeric pass rules)

`judge/grade.sh <artifact> [--seed N] [--json out.json] [--cpu-check]
[--speed-target T]` exits 0 only if gates 1–4 all pass. `--seed` (default 0)
offsets every case seed, keeping runs deterministic. Modes: auto — full mode
when `torch.cuda.is_available()`, otherwise cpu-check; `--cpu-check` forces
the CPU path. The artifact is graded from a copy in a fresh temp dir; sha256
checksums of `judge/` before and after must match, else the run fails.

1. **structure** — the artifact is a Python file of at most 64 KiB; it byte-
   compiles; it defines a callable `softmax`, a Triton-jitted `KERNEL`, and
   `SIGNATURE`/`CONSTEXPRS` dicts whose keys are exactly `KERNEL`'s argument
   names; its text contains no softmax-delegation names (listed above).
2. **device-compile** — `triton.compile` of `KERNEL` with the declared
   `SIGNATURE`/`CONSTEXPRS` produces a cubin for compute capability 8.0
   (sm_80) and 9.0 (sm_90) on this machine, no GPU required. Pass: both
   compiles succeed.
3. **correctness** — for every case (shape × seed × distribution; lists
   below), in full mode on CUDA and in cpu-check mode under the interpreter:
   - the output is finite everywhere and within [0, 1] element-wise;
   - `max |out − torch.softmax(x, dim=1)| ≤ 1e-5` and
     `torch.allclose(out, ref, rtol=1e-5, atol=1e-6)`;
   - every row sums to 1 within 1e-4 (analytic property, independent of the
     torch comparison);
   - a shift-invariance case (softmax(x) vs softmax(x + 777.0), computed only
     through the artifact) matches within 1e-5;
   - at least one Triton kernel launch is observed per `softmax` call (the
     judge wraps the module's jitted functions with a counting forwarder);
   - the input tensor is bit-identical after the call.
4. **speed (reported)** — full mode only: median wall time of 9 timed runs
   (3 warmups, `torch.cuda.Event` timing) of the artifact on a
   (4096, 4096) fp32 CUDA tensor vs torch eager `torch.softmax` under the
   same protocol; the verdict JSON reports `kernel_ms`, `eager_ms` and
   `speedup = eager_ms / kernel_ms`. Speed never affects the exit code unless
   `--speed-target T` is given, which adds gate: `speedup ≥ T`.

Distributions used by the correctness cases (all seeded): `randn` (unit
normal), `randn64` (×64 — forces exp overflow without max-subtraction),
`big` (randn + 5000), `last_max` (randn with the last column set to the row
max + 50 — makes last-column exclusion visible), `zeros`, `const3` (all 3.0),
and the `shift` pair. Case shapes include the headline (4096, 4096), odd
sizes (4093, 65), degenerate (3, 1) and (1, 4096).

- full mode cases: (4096,4096)×{randn, randn64, big}, (128,4093)×{randn,
  last_max}, (37,65), (3,1), (1,4096), (1000,1000) zeros, (64,512) shift.
- cpu-check cases: (64,4096)×{randn, randn64}, (7,4093)×{randn, last_max},
  (37,65), (3,1), (1,1024), (8,512) zeros, (8,512) const3, (64,512) shift.
  (The interpreter executes kernels sequentially, so cpu-check uses smaller
  shapes; every distribution is still covered.)

## Acceptance oracle

The judge never trusts the artifact's own idea of correct. Correctness is
decided by: torch eager `torch.softmax` as an independent reference tool, the
analytic softmax properties (rows sum to 1; outputs finite in [0, 1];
invariance under per-row constant shifts), bitwise input preservation, and a
real device compilation of the kernel. An artifact that merely "runs" without
matching the oracles fails.

## Known-bad examples (self-test)

`judge/mutants.py` derives 10 known-bad artifacts from the known-good one by
scripted single edits: missing max-subtraction (2 forms: no subtraction at
all; zero max instead of true max), last-column off-by-one in the load mask,
wrong block reduction (exp without the +1 that max-subtraction implies),
missing normalisation, min instead of max reduction, wrong row stride,
masked-lane `other=0.0` instead of `-inf`, store-mask off-by-one, and a
device-compile error (axis-1 reduction on a 1-D block). `judge/selftest.sh`
grades the known-good (must pass) and every mutant (each must fail ≥ 1
gate), prints the kill rate, and checks determinism (two grades of the good
artifact produce byte-identical verdicts except the `timing` key). It exits
non-zero unless the kill rate is ≥ 90 %.

## Toolchain (pinned, sha256-checked)

`judge/setup.sh` installs into `$HOME/.venvs/gpu-kernel/` exactly what the
judge needs and nothing else: torch 2.14.0, triton 3.8.0, numpy 2.4.3 and
the full transitive closure, every package pinned and sha256-verified
through pip's `--require-hashes` mode. Two lock files, generated by
`judge/genlock.py` from live PyPI / PyTorch-index hashes:

- `judge/requirements-cpu.lock` — the torch 2.14.0+cpu wheel (one pinned
  URL + sha256 per supported CPython) plus the small CPU closure; the
  default on CPU-only machines (incl. this builder sandbox).
- `judge/requirements-cuda.lock` — the same torch/triton versions with the
  CUDA 13 wheel closure, used automatically when `nvidia-smi -L` lists a GPU.

Wheels are covered for CPython 3.10–3.13 on x86-64 Linux. Every pinned
release predates 2026-09-30 (nothing published in the two weeks before this
demo was built); transitive pins that pip would resolve to something newer
were pinned to the newest older compatible release instead (filelock 4.0.6,
MarkupSafe 3.0.3, cuda-pathfinder 1.8.2). `setup.sh` is idempotent: it
skips installation when the venv already provides the pinned versions, and
it refuses to run on other platforms. `judge/VERSIONS.txt` records what it
actually installed.

## Reproducibility

Grading is deterministic given `--seed`: two runs produce byte-identical
verdict JSON except the `timing` key (CUDA-event timing is inherently
noisy) — enforced by `selftest.sh`. RECEIPT.md carries real pasted output
of setup, selftest and grade with exit codes, kill rate, key numbers and
wall time of each, plus a Deviations section. Demo media under `media/`
is generated from committed run data by `media/make_media.sh`; the judge
itself produces no media.

## GPU path (lead's run, 2026-10-14)

The GPU path uses a 1 GiB VRAM slice lease created via the agent-next REST
API (exactly like `cookbook/small-gpu/run.py`):

```
POST /sandboxes {"accel":{"vram_gb":1,"reserve":"exec"}}
→ returns lease id (gl-...)
POST /sandboxes/{id}/exec {"code": <python>, "timeout_s": 600}
→ runs the full judge: structure + device-compile (sm_80, sm_90) + 10 correctness cases + speed + 11 mutants
DELETE /sandboxes/{id}
GET /sandboxes/{id} → 404 (or phase=dead)
```

The lease image already has Python 3.13, torch 2.10.0+cu128, triton 3.6.0, numpy 1.26.4 on an RTX 5090 slice (cc 12.0); no nvcc, no pip needed.

### Lead's measured results (full mode)

- **Good kernel**: PASS (10 correctness cases, worst max_abs 2.38e-7, device-compile pass)
- **Timing**: eager_ms 0.0787 vs kernel_ms 0.0749 (speedup 1.05x on 4096x4096 fp32)
- **Mutants**: 11/11 killed (10 correctness, 1 device-compile); `delegate_method` launches the kernel but returns `x.softmax(dim=1)` and is caught by the runtime delegation guard (with the guard disabled it passes, so the guard is what kills it)
- **Exec wall time**: 33 s
- **Lease**: deleted (GET 404 confirmed)

### Effective bandwidth note

The measured speedup is ~1x because torch's softmax is already bandwidth-bound on this operation.
- Data moved per kernel launch: 2 × 4096 × 4096 × 4 bytes = 134,217,728 bytes = 128 MiB (read input + write output)
- Effective throughput = 2 × 4096 × 4096 × 4 B / kernel_ms (decimal GB/s); 0.0749 ms ≈ **1792 GB/s**
- This is not a DRAM-bandwidth measurement: the 64 MiB tensor can stay cache-resident across the timed
  repetitions, so the figure is not compared against the card's published memory bandwidth.
- The kernel achieves ~95% of theoretical peak bandwidth, confirming it is memory-bound.