# gpu-sim-sweep demo — receipt

Real output, all measured. Two kinds of machine were used:

- **Builder sandbox** (Debian, x86-64, CPython 3.12, **no GPU**) — ran
  `judge/setup.sh` and `judge/selftest.sh` in cpu-check mode (the mode
  the judge auto-selects when `warp.is_cuda_available()` is false).
- **agent-next GPU leases** (4 GiB VRAM slices, RTX 5090, Python 3.13.5,
  mujoco / mujoco-warp 3.8.1, warp-lang 1.13.0 preinstalled) — fresh
  leases, each created and destroyed by `python3 run.py --gpu`. Each grade
  on the lease runs the simulation itself: the artifact is config only.

Commands run from `cookbook/gpu-sim-sweep/` on 2026-10-15.

## bash judge/setup.sh (builder sandbox)

```
$ bash judge/setup.sh
setup.sh: creating venv at /home/user/.venvs/gpu-sim-sweep
Collecting mujoco==3.8.1 ...
  Downloading mujoco-3.8.1-cp312-cp312-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl (7.3 MB)
Collecting mujoco-warp==3.8.1 ...
Collecting warp-lang==1.13.0 ...
  Downloading warp_lang-1.13.0-py3-none-manylinux_2_28_x86_64.whl (138.3 MB)
Collecting numpy==1.26.4 ... absl-py==2.5.1 ... etils==1.14.0 ...
glfw==2.10.2 ... pyopengl==3.1.10 ... fsspec==2026.9.0 ...
typing-extensions==4.16.0 ... zipp==4.1.1 ...
Successfully installed absl-py-2.5.1 etils-1.14.0 fsspec-2026.9.0 glfw-2.10.2
mujoco-3.8.1 mujoco-warp-3.8.1 numpy-1.26.4 pyopengl-3.1.10
typing-extensions-4.16.0 warp-lang-1.13.0 zipp-4.1.1
setup.sh: ok
exit=0
```

(Wheel download progress lines trimmed; every install went through pip's
`--require-hashes` against `judge/requirements.lock`. What it installed is
recorded in `judge/VERSIONS.txt`.)

## bash judge/selftest.sh (builder sandbox, cpu-check mode)

```
$ bash judge/selftest.sh
selftest: generating mutants
selftest: grading known-good (auto mode)
selftest: known-good: PASS (mode: cpu-check)
selftest: mutant smuggled_results: killed (gate: structure)
selftest: mutant gravity_flipped: killed (gate: structure)
selftest: mutant missing_nconmax: killed (gate: structure)
selftest: mutant tiny_timestep: killed (gate: cost)
selftest: mutant short_settle: killed (gate: cost)
selftest: mutant solver_iter_1: killed (gate: cpu-physics)
selftest: mutant low_capacity: skipped (needs gpu, mode is cpu-check)
selftest: mutant over_ladder: skipped (needs gpu, mode is cpu-check)
selftest: kill rate: 6/6 = 100% (2 gpu-only skipped)
selftest: determinism check (two grades of the good config)
Warp CUDA warning: Could not find or load the NVIDIA CUDA driver. GPU execution will not be available.
Warp CUDA warning: Could not find or load the NVIDIA CUDA driver. GPU execution will not be available.
selftest: determinism: OK
selftest: ok
exit=0
```

## python3 run.py --gpu — run 1 (fresh lease gl-3f66cf-3)

```
$ python3 run.py --gpu
create GPU lease (4 GiB VRAM slice)...
created gl-3f66cf-3 (4 GiB VRAM slice)
exec unpack + mutant generation on GPU lease...
  [unpack] exec ok (0 s)
lease python 3.13.5; 8 mutants generated
grade known-good (full mode: CPU baseline + real GPU sweep; first grade pays the Warp cold-compile)...
  [grade good] exec ok (145 s)
  [grade smuggled_results] exec ok (1 s)
  [grade gravity_flipped] exec ok (2 s)
  [grade missing_nconmax] exec ok (1 s)
  [grade tiny_timestep] exec ok (0 s)
  [grade short_settle] exec ok (1 s)
  [grade solver_iter_1] exec ok (49 s)
  [grade low_capacity] exec ok (83 s)
  [grade over_ladder] exec ok (90 s)

gpu-sim-sweep demo: PASS (mode full)
  gate cost: pass
  gate cpu-parity: pass
  gate engine-parity: pass
  gate physics-oracle: pass
  gate structure: pass
  gate throughput: pass
  measured sweep (judge-ran, 4 GiB slice):
   nworld |     steps/s | arm err |            box z | 1st step s
        1 |         206 |   0.036 | [0.315,0.315] |      86.30
       64 |      11,785 |   0.036 | [0.315,0.315] |       0.01
      512 |      80,685 |   0.036 | [0.315,0.315] |       0.01
     2048 |     275,739 |   0.036 | [0.315,0.315] |       0.01
     8192 |     645,390 |   0.036 | [0.315,0.315] |       0.02
  CPU 27,100 steps/s, top GPU 645,390 steps/s (speedup x23.8, floor x4.0)
  cold Warp compile (first step): 86.303 s; parity max err 0.008110745441113454 rad

mutants: 8/8 killed
  gravity_flipped: FAIL (structure)
  low_capacity: FAIL (cpu-parity, physics-oracle, throughput)
  missing_nconmax: FAIL (structure)
  over_ladder: FAIL (physics-oracle, throughput)
  short_settle: FAIL (cost)
  smuggled_results: FAIL (structure)
  solver_iter_1: FAIL (cpu-parity, throughput)
  tiny_timestep: FAIL (cost)
destroying gl-3f66cf-3...
destroyed gl-3f66cf-3; verified absent or dead
total: 377 s
exit=0
```

## python3 run.py --gpu — run 2 (fresh lease gl-3f66cf-7)

```
$ python3 run.py --gpu --report-json media/data/report.json
create GPU lease (4 GiB VRAM slice)...
created gl-3f66cf-7 (4 GiB VRAM slice)
exec unpack + mutant generation on GPU lease...
  [unpack] exec ok (0 s)
lease python 3.13.5; 8 mutants generated
grade known-good (full mode: CPU baseline + real GPU sweep; first grade pays the Warp cold-compile)...
  [grade good] exec ok (163 s)
  [grade smuggled_results] exec ok (0 s)
  [grade gravity_flipped] exec ok (0 s)
  [grade missing_nconmax] exec ok (0 s)
  [grade tiny_timestep] exec ok (0 s)
  [grade short_settle] exec ok (0 s)
  [grade solver_iter_1] exec ok (59 s)
  [grade low_capacity] exec ok (78 s)
  [grade over_ladder] exec ok (84 s)
wrote exec report: media/data/report.json

gpu-sim-sweep demo: PASS (mode full)
  gate cost: pass
  gate cpu-parity: pass
  gate engine-parity: pass
  gate physics-oracle: pass
  gate structure: pass
  gate throughput: pass
  measured sweep (judge-ran, 4 GiB slice):
   nworld |     steps/s | arm err |            box z | 1st step s
        1 |         122 |   0.036 | [0.315,0.315] |      96.52
       64 |       7,116 |   0.036 | [0.315,0.315] |       0.01
      512 |      60,842 |   0.036 | [0.315,0.315] |       0.01
     2048 |     222,929 |   0.036 | [0.315,0.315] |       0.01
     8192 |     557,066 |   0.036 | [0.314,0.315] |       0.02
  CPU 35,681 steps/s, top GPU 557,066 steps/s (speedup x15.6, floor x4.0)
  cold Warp compile (first step): 96.52 s; parity max err 0.008110745441113454 rad

mutants: 8/8 killed
  gravity_flipped: FAIL (structure)
  low_capacity: FAIL (cpu-parity, physics-oracle)
  missing_nconmax: FAIL (structure)
  over_ladder: FAIL (physics-oracle, throughput)
  short_settle: FAIL (cost)
  smuggled_results: FAIL (structure)
  solver_iter_1: FAIL (cpu-parity)
  tiny_timestep: FAIL (cost)
destroying gl-3f66cf-7...
destroyed gl-3f66cf-7; verified absent or dead
total: 390 s
exit=0
```

The full output of run 2 is also committed at
[`media/data/gpu-run.log`](media/data/gpu-run.log), and its exec report at
[`media/data/report.json`](media/data/report.json) — that file is the source
data for every figure and frame under `media/`.

## Key numbers, side by side

| | run 1 (gl-3f66cf-3) | run 2 (gl-3f66cf-7) |
|---|---:|---:|
| verdict | PASS, exit 0, mode `full` | PASS, exit 0, mode `full` |
| mutants killed | 8/8 | 8/8 |
| end-to-end wall | 377 s | 390 s |
| good-grade wall (incl. cold compile) | 145 s | 163 s |
| slowest mutant grade | 90 s (over_ladder) | 84 s (over_ladder) |
| cold Warp compile (first step) | 86.3 s | 96.5 s |
| CPU baseline, steps/s | 27,100 | 35,681 |
| GPU nworld=1 | 206 | 122 |
| GPU nworld=64 | 11,785 | 7,116 |
| GPU nworld=512 | 80,685 | 60,842 |
| GPU nworld=2048 | 275,739 | 222,929 |
| GPU nworld=8192 | 645,390 | 557,066 |
| speedup (gate floor ×4) | ×23.8 | ×15.6 |
| CPU↔GPU world-0 parity err | 0.00811 rad | 0.00811 rad |
| arm tracking err (all points) | 0.036 rad | 0.036 rad |
| resting box z | 0.315 | 0.315 (min 0.314 @8192) |
| engine parity | mujoco 3.8.1 == 3.8.1 | mujoco 3.8.1 == 3.8.1 |

Toolchain on both leases (from the measured verdict): mujoco 3.8.1,
mujoco-warp 3.8.1, warp 1.13.0, Python 3.13.5.

Observed mutant kills (from the run-2 verdicts; run 1 identical except as
noted): the three structure mutants and the two cost mutants
(`tiny_timestep` — settle window 0.08 s of sim time outside [0.4, 4.0];
`short_settle` — 0.02 s) were rejected before any sim ran, in ~1 s of exec
time each; `solver_iter_1` — world-0 parity err 131 rad (run 1 also tripped
the throughput gate); `low_capacity` — measured tunnelling, box min z
−5.68 at nworld=64 plus world-0 parity err 0.067 rad; `over_ladder` —
`put_data` at nworld=65536 raised `MemoryError` (clean observed OOM,
counted as a failed point, not a crash), and the top point produced no
throughput measurement.

## Deviations

- The builder sandbox has no GPU, so `judge/selftest.sh` ran in cpu-check
  mode: the two gpu-tagged mutants (`low_capacity`, `over_ladder`) were
  skipped there and killed for real on the GPU leases (8/8 both runs).
- `run.py --gpu` does not run `judge/setup.sh` on the lease — the slice image
  already ships the pinned toolchain (verified by the engine-parity gate:
  GPU-reported mujoco 3.8.1 == CPU-measured 3.8.1). `setup.sh`/`selftest.sh`
  were exercised locally instead, above.
- Between the two runs above, a third attempt on lease `gl-3f66cf-6` died
  mid-run when the platform returned HTTP 500 on the `low_capacity` exec:
  `run.py` printed the error body, still deleted the lease (through a
  gateway-restart 503 on the first DELETE, retried) and confirmed it gone,
  and exited 1. That is the designed failure path, not a demo defect; the
  run was simply repeated.
- CPU and GPU steps/s vary with lease contention (27.1k vs 35.7k CPU; the
  nworld=1 point especially, 206 vs 122); the throughput gate is a ratio
  against the same run's CPU baseline, so both runs cleared the ×4 floor
  by a wide margin.
- The parity error is byte-identical across runs (0.008110745441113454 rad):
  the sim itself is deterministic; only wall-clock and throughput numbers
  move. They live under `timing` in the verdict, which the determinism check
  excludes.
- `REPRODUCE.md` is left for the independent-reproduction pass by a different
  agent before merge, per `cookbook/DEMO-STANDARD.md`.
