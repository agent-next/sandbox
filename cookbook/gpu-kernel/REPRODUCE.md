# gpu-kernel demo — reproduction report

Reproduced from `README.md` and `SPEC.md` in a fresh sandbox (this repo at `sbx/demo-gpu-kernel-repro`, Debian x86-64, 2 vCPU, ~4 GB RAM, **no GPU**, CPython 3.12). All commands run from `cookbook/gpu-kernel/`. Judge ran in `--cpu-check` mode throughout (offline device compile + Triton interpreter numerics).

---

## 1. Setup

```bash
$ time bash judge/setup.sh
setup.sh: creating venv at /home/user/.venvs/gpu-kernel (cpu closure)
[notice] A new release of pip is available: 25.0.1 -> 26.2.1
Ignoring torch: markers 'python_version == "3.10"' don't match your environment
Ignoring torch: markers 'python_version == "3.11"' don't match your environment
Collecting torch@ https://download.pytorch.org/whl/cpu/torch-2.14.0%2Bcpu-cp312-cp312-manylinux_2_28_x86_64.whl ...
Collecting triton==3.8.0 ...
Collecting numpy==2.4.3 ...
...
Successfully installed filelock-4.0.6 fsspec-2026.9.0 jinja2-3.1.6 markupsafe-3.0.3 mpmath-1.3.0 networkx-3.7 numpy-2.4.3 setuptools-84.0.0 sympy-1.14.0 torch-2.14.0+cpu triton-3.8.0 typing-extensions-4.16.0
setup.sh: ok (cpu)

real    1m3.815s
user    0m43.971s
sys     0m17.042s
exit=0
```

**Toolchain installed** (from `judge/VERSIONS.txt`):
- torch 2.14.0+cpu
- triton 3.8.0
- numpy 2.4.3
- python 3.12

**Match with RECEIPT.md**: ✓ exact same pinned versions. Wall time 64s vs RECEIPT 50s (wheel downloads; RECEIPT had warm cache).

---

## 2. Self-test

```bash
$ time bash judge/selftest.sh
selftest: generating mutants
selftest: grading known-good
selftest: known-good: PASS
selftest: mutant no_max_sub: killed (gate: correctness)
selftest: mutant no_max_sub_other_form: killed (gate: correctness)
selftest: mutant off_by_one: killed (gate: correctness)
selftest: mutant wrong_block_reduction: killed (gate: correctness)
selftest: mutant no_normalise: killed (gate: correctness)
selftest: mutant min_for_max: killed (gate: correctness)
selftest: mutant wrong_row_stride: killed (gate: correctness)
selftest: mutant compile_error: killed (gate: device-compile)
selftest: mutant masked_other_zero: killed (gate: correctness)
selftest: mutant store_off_by_one: killed (gate: correctness)
selftest: kill rate: 10/10 = 100%
selftest: determinism check (two grades of the good artifact)
selftest: determinism: OK
selftest: ok

real    1m49.896s
user    1m29.756s
sys     0m18.051s
exit=0
```

| Metric | RECEIPT.md | This run | Match? |
|---|---|---|---|
| Kill rate | 10/10 = 100% | 10/10 = 100% | ✓ |
| Mutants killed (by gate) | 9 correctness, 1 device-compile | 9 correctness, 1 device-compile | ✓ |
| Good kernel passes | PASS | PASS | ✓ |
| Determinism | OK | OK | ✓ |
| Exit code | 0 | 0 | ✓ |
| Wall time | 1m52.161s | 1m49.896s | ≈ |

**SPEC tolerance**: kill rate ≥ 90% → 100% ✓

---

## 3. Grade good kernel (seed 0, cpu-check)

```bash
$ time bash judge/grade.sh examples/good/kernel.py --json /tmp/v.json
{
  "artifact": "kernel.py",
  "cases": [...],
  "gates": {
    "correctness": { "cases": 10, "failed": [], "pass": true,
      "worst": { "max_abs": 1.1920928955078125e-07, "rowsum": 1.1920928955078125e-07, "shift": 1.0468065738677979e-06 }},
    "device-compile": { "pass": true, "problems": [] },
    "structure": { "pass": true, "problems": [] }
  },
  "judge_intact": true,
  "mode": "cpu-check",
  "seed": 0,
  "timing": {}
}

real    0m11.038s
user    0m9.051s
sys     0m1.497s
exit=0
```

### Key metrics vs RECEIPT.md (seed 0, cpu-check)

| Metric | RECEIPT.md | This run | SPEC limit | Match? |
|---|---|---|---|---|
| `mode` | cpu-check | cpu-check | — | ✓ |
| `judge_intact` | true | true | — | ✓ |
| Worst `max_abs_err` | 1.19e-07 | 1.19e-07 | ≤ 1e-5 | ✓ |
| Worst `rowsum_err` | 1.19e-07 | 1.19e-07 | ≤ 1e-4 | ✓ |
| Worst `shift_err` | 1.05e-06 | 1.05e-06 | ≤ 1e-5 | ✓ |
| Cases passed | 10/10 | 10/10 | — | ✓ |
| Exit code | 0 | 0 | — | ✓ |
| Wall time | 10.482s | 11.038s | — | ≈ |

All numeric values **byte-identical** to RECEIPT.md.

---

## 4. Determinism check (two grades, same seed, ignore `timing`)

```bash
$ bash judge/grade.sh examples/good/kernel.py --cpu-check --json /tmp/det1.json >/dev/null
$ bash judge/grade.sh examples/good/kernel.py --cpu-check --json /tmp/det2.json >/dev/null
$ python3 -c "import json; a=json.load(open('/tmp/det1.json')); b=json.load(open('/tmp/det2.json')); a.pop('timing',None); b.pop('timing',None); print('Identical:', a==b)"
Identical: True
```

**Result**: ✓ **identical** (ignoring `timing` key). Matches RECEIPT.md "determinism: OK" and SPEC reproducibility guarantee.

---

## 5. Media rebuild from committed GPU data

```bash
$ time bash media/make_media.sh
make_media.sh: creating venv at media/.venv
...
wrote /home/user/w/cookbook/gpu-kernel/media/result.png
wrote /home/user/w/cookbook/gpu-kernel/media/loop.png
wrote /home/user/w/cookbook/gpu-kernel/media/demo.mp4 (1127 frames, 37.6 s, 1920x1080 @30 fps, libx264 crf 18)
wrote MANIFEST.json

real    0m53.217s
user    1m12.645s
sys     0m5.115s
exit=0
```

### SHA-256 comparison with `media/MANIFEST.json`

| Output | MANIFEST.json (committed) | Rebuilt | Match? |
|---|---|---|---|
| `result.png` | 44db38675ba6e9510a31c670e058cd84c61e1adaebd37b16e483a2a9f1bc725e | 44db38675ba6e9510a31c670e058cd84c61e1adaebd37b16e483a2a9f1bc725e | ✓ bit-identical |
| `loop.png` | d870ca0eb4f84f636adb590a991bf37e11cb6ceadbe10249775da81ccb013cb8 | d870ca0eb4f84f636adb590a991bf37e11cb6ceadbe10249775da81ccb013cb8 | ✓ bit-identical |
| `demo.mp4` | d36a32b04a833fd63e994de477a7cfd0437c8fdf1b0489fc4b8481b7115e9312 | d36a32b04a833fd63e994de477a7cfd0437c8fdf1b0489fc4b8481b7115e9312 | ✓ bit-identical |

**Source data unchanged** (verified):
- `data/gpu-run.log`: 2b04891cf6cebf7c841242dc08217329e945c5df293601de5d52d661002aa98c ✓
- `data/report.json`: 3f88c3f16953dec17fab66051d6d6850bd806d8467b3ba71140f817ececad518 ✓

### Video properties
- Resolution: 1920×1080 (REVIEW.md expects 1920×1080) ✓
- Frame rate: 30 fps (REVIEW.md expects ~30 fps) ✓
- Duration: 37.6 s (REVIEW.md expects 30-45 s) ✓
- Codec: libx264 CRF 18 ✓

**Note**: Video is **bit-identical** to committed version (encoder is deterministic with fixed inputs and pinned ffmpeg). PNGs are also bit-identical. The underlying data files (`data/report.json`, `data/gpu-run.log`) match exactly.

---

## 6. README.md step coverage & issues

| Step in README | Status | Notes |
|---|---|---|
| `python3 cookbook/gpu-kernel/run.py` (CPU) | **Not run** | Requires `sbx` CLI and `SBX_API_KEY` (external service). Verified via in-sandbox sequence instead (see below). |
| `python3 cookbook/gpu-kernel/run.py --gpu` | **Not run** | Requires GPU lease via REST API; no GPU access in this sandbox. |
| `bash cookbook/gpu-kernel/judge/setup.sh` | ✓ Done | Works as documented. |
| `bash cookbook/gpu-kernel/judge/selftest.sh` | ✓ Done | Works as documented. |
| `bash cookbook/gpu-kernel/judge/grade.sh examples/good/kernel.py` | ✓ Done | Works as documented. |
| `bash cookbook/gpu-kernel/media/make_media.sh` | ✓ Done | Works as documented (needs ffmpeg). |

### In-sandbox sequence verification (from RECEIPT.md §run.py sequence verification)

```bash
git clone --depth 1 -b <ref> https://github.com/agent-next/sandbox sandbox   # 1 s, exit 0
bash sandbox/cookbook/gpu-kernel/judge/setup.sh                              # cold: 59 s, exit 0
bash sandbox/cookbook/gpu-kernel/judge/selftest.sh                           # 1m50s, exit 0 (10/10)
bash sandbox/cookbook/gpu-kernel/judge/grade.sh sandbox/cookbook/gpu-kernel/examples/good/kernel.py --json /tmp/v.json  # 11 s, exit 0
```

The above sequence is what `run.py` sends to `sbx exec`; it was **verified by the lead** and the CPU path was reproduced here directly.

### Unclear / missing / wrong steps in README

1. **`run.py` one-command run** — Requires external `sbx` CLI and `SBX_API_KEY`. The README presents it as a simple local command but it actually creates remote sandboxes/GPU leases via REST API. A user without agent-next account/API key cannot run it. The README should clarify this is a remote orchestration command, not a local script.

2. **GPU path prerequisites** — The `--gpu` flag needs a GPU lease created via REST API (not local hardware). The README says "GPU access on your key" but doesn't explain how to obtain `SBX_API_KEY` or what the lease API is.

3. **Local CPU-only path** — The "try the judge locally" section (lines 39-45) is the actual runnable path for CPU-only machines. It works and is well-specified.

4. **Media rebuild** — Requires `ffmpeg` + `ffprobe` on PATH. The README mentions this but not that they must be installed system-wide (not in venv). Also `data/report.json` must exist (only produced by a real GPU run by the lead).

---

## 7. GPU path (read-only verification)

This sandbox has **no GPU**. The GPU path numbers are taken from the committed `media/data/report.json` (lead's run on RTX 5090 slice, 2026-10-14):

| Metric | Lead's GPU run (from `data/report.json`) | SPEC |
|---|---|---|
| Mode | full | — |
| `eager_ms` | 0.078528 | — |
| `kernel_ms` | 0.076224 | — |
| `speedup` | 1.030x | reported only |
| Worst `max_abs` | 2.38e-07 | ≤ 1e-5 ✓ |
| Worst `rowsum` | 2.38e-07 | ≤ 1e-4 ✓ |
| Worst `shift` | 1.05e-06 | ≤ 1e-5 ✓ |
| Mutants killed | 10/10 | ≥ 90% ✓ |
| Exec wall time | 33 s | — |

No claim is made about reproducing the GPU path — only the CPU path (`--cpu-check`) was reproduced here.

---

## 8. Verdict

**VERDICT: REPRODUCED**

All CPU-path steps from README.md succeed with exit code 0. Every numeric result (kill rate, worst errors, gate verdicts, toolchain versions) matches RECEIPT.md within SPEC tolerances. The two-run determinism check passes (verdict JSONs identical ignoring `timing`). Media rebuild produces bit-identical PNGs and MP4 (sha256s match MANIFEST.json exactly). The only steps not run are the `run.py` commands that require external `sbx` CLI/API key and GPU lease — these are documented as external orchestration, not local execution.

---

## 9. Clean-up

Scratch files deleted: `/tmp/v.json`, `/tmp/det1.json`, `/tmp/det2.json`. No other sandbox-created files outside the repo.
> Note: this reproduction ran against the judge before the review round that
> added the runtime delegation guard and the 11th mutant (see RECEIPT.md,
> "Review round"). The guard was then power-checked and the self-test re-run
> (11/11) in a fresh sandbox.
