# gpu-sim-sweep demo — receipt

Real output, all measured. Two kinds of machine were used:

- **Builder sandbox** (Debian, x86-64, CPython 3.12, **no GPU**) — ran
  `judge/setup.sh` and `judge/selftest.sh` in `--cpu-check` mode (the mode
  the judge auto-selects when `warp.is_cuda_available()` is false).
- **agent-next GPU leases** (4 GiB VRAM slices, RTX 5090, Python 3.13.5,
  mujoco / mujoco-warp 3.8.1, warp-lang 1.13.0 preinstalled) — two fresh
  leases, each created and destroyed by `python3 run.py --gpu`. Each grade
  on the lease runs the simulation itself: the artifact is config only.

Commands run from `cookbook/gpu-sim-sweep/` on 2026-10-14.

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
selftest: mutant tiny_timestep: killed (gate: cpu-physics)
selftest: mutant short_settle: killed (gate: cpu-physics)
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

## python3 run.py --gpu — run 1 (fresh lease gl-951d38-18)

```
$ python3 run.py --gpu --report-json report.json
create GPU lease (4 GiB VRAM slice)...
created gl-951d38-18 (4 GiB VRAM slice)
exec unpack + mutant generation on GPU lease...
  [unpack] exec ok (2 s)
lease python 3.13.5; 8 mutants generated
grade known-good (full mode: CPU baseline + real GPU sweep; first grade pays the Warp cold-compile)...
  [grade good] exec ok (131 s)
  [grade smuggled_results] exec ok (1 s)
  [grade gravity_flipped] exec ok (0 s)
  [grade missing_nconmax] exec ok (0 s)
  [grade tiny_timestep] exec ok (51 s)
  [grade short_settle] exec ok (23 s)
  [grade solver_iter_1] exec ok (47 s)
  [grade low_capacity] exec ok (92 s)
  [grade over_ladder] exec ok (78 s)
wrote exec report: report.json

gpu-sim-sweep demo: PASS (mode full)
  gate cpu-parity: pass
  gate engine-parity: pass
  gate physics-oracle: pass
  gate structure: pass
  gate throughput: pass
  measured sweep (judge-ran, 4 GiB slice):
   nworld |     steps/s | arm err |            box z | 1st step s
        1 |         241 |   0.036 | [0.315,0.315] |      82.75
       64 |      13,528 |   0.036 | [0.315,0.315] |       0.00
      512 |      82,075 |   0.036 | [0.315,0.315] |       0.01
     2048 |     309,514 |   0.036 | [0.315,0.315] |       0.02
     8192 |     724,840 |   0.036 | [0.314,0.315] |       0.02
  CPU 24,202 steps/s, top GPU 724,840 steps/s (speedup x29.9, floor x4.0)
  cold Warp compile (first step): 82.749 s; parity max err 0.008110745441113454 rad

mutants: 8/8 killed
  gravity_flipped: FAIL (structure)
  low_capacity: FAIL (cpu-parity, physics-oracle)
  missing_nconmax: FAIL (structure)
  over_ladder: FAIL (physics-oracle, throughput)
  short_settle: FAIL (physics-oracle)
  smuggled_results: FAIL (structure)
  solver_iter_1: FAIL (cpu-parity)
  tiny_timestep: FAIL (physics-oracle)
destroying gl-951d38-18...
destroyed gl-951d38-18; verified absent or dead
total: 432 s
exit=0
```

## python3 run.py --gpu — run 2 (fresh lease gl-951d38-20)

```
$ python3 run.py --gpu --report-json report.json
create GPU lease (4 GiB VRAM slice)...
created gl-951d38-20 (4 GiB VRAM slice)
exec unpack + mutant generation on GPU lease...
  [unpack] exec ok (1 s)
lease python 3.13.5; 8 mutants generated
grade known-good (full mode: CPU baseline + real GPU sweep; first grade pays the Warp cold-compile)...
  [grade good] exec ok (139 s)
  [grade smuggled_results] exec ok (0 s)
  [grade gravity_flipped] exec ok (0 s)
  [grade missing_nconmax] exec ok (0 s)
  [grade tiny_timestep] exec ok (57 s)
  [grade short_settle] exec ok (21 s)
  [grade solver_iter_1] exec ok (41 s)
  [grade low_capacity] exec ok (93 s)
  [grade over_ladder] exec ok (105 s)
wrote exec report: report.json

gpu-sim-sweep demo: PASS (mode full)
  gate cpu-parity: pass
  gate engine-parity: pass
  gate physics-oracle: pass
  gate structure: pass
  gate throughput: pass
  measured sweep (judge-ran, 4 GiB slice):
   nworld |     steps/s | arm err |            box z | 1st step s
        1 |         216 |   0.036 | [0.315,0.315] |      88.38
       64 |      12,687 |   0.036 | [0.315,0.315] |       0.01
      512 |      87,599 |   0.036 | [0.315,0.315] |       0.01
     2048 |     280,627 |   0.036 | [0.315,0.315] |       0.01
     8192 |     754,416 |   0.036 | [0.315,0.315] |       0.01
  CPU 33,617 steps/s, top GPU 754,416 steps/s (speedup x22.4, floor x4.0)
  cold Warp compile (first step): 88.382 s; parity max err 0.008110745441113454 rad

mutants: 8/8 killed
  gravity_flipped: FAIL (structure)
  low_capacity: FAIL (cpu-parity, physics-oracle)
  missing_nconmax: FAIL (structure)
  over_ladder: FAIL (physics-oracle, throughput)
  short_settle: FAIL (physics-oracle)
  smuggled_results: FAIL (structure)
  solver_iter_1: FAIL (cpu-parity, throughput)
  tiny_timestep: FAIL (physics-oracle)
destroying gl-951d38-20...
destroyed gl-951d38-20; verified absent or dead
total: 462 s
exit=0
```

## Key numbers, side by side

| | run 1 (gl-951d38-18) | run 2 (gl-951d38-20) |
|---|---:|---:|
| verdict | PASS, exit 0, mode `full` | PASS, exit 0, mode `full` |
| mutants killed | 8/8 | 8/8 |
| end-to-end wall | 432 s | 462 s |
| good-grade wall (incl. cold compile) | 131 s | 139 s |
| cold Warp compile (first step) | 82.7 s | 88.4 s |
| CPU baseline, steps/s | 24,202 | 33,617 |
| GPU nworld=1 | 241 | 216 |
| GPU nworld=64 | 13,528 | 12,687 |
| GPU nworld=512 | 82,075 | 87,599 |
| GPU nworld=2048 | 309,514 | 280,627 |
| GPU nworld=8192 | 724,840 | 754,416 |
| speedup (gate floor ×4) | ×29.9 | ×22.4 |
| CPU↔GPU world-0 parity err | 0.00811 rad | 0.00811 rad |
| arm tracking err (all points) | 0.036 rad | 0.036 rad |
| resting box z | 0.315 (min 0.314 @8192) | 0.315 |
| engine parity | mujoco 3.8.1 == 3.8.1 | mujoco 3.8.1 == 3.8.1 |

Toolchain on both leases (from the measured verdict): mujoco 3.8.1,
mujoco-warp 3.8.1, warp 1.13.0, Python 3.13.5.

Observed mutant kills (from the run-1 verdicts; run 2 identical except as
noted): `low_capacity` — measured tunnelling, box min z −5.74 at nworld=64
plus world-0 parity err 0.067 rad; `over_ladder` — `put_data` at nworld=65536
raised `MemoryError` (clean observed OOM, counted as a failed point, not a
crash); `solver_iter_1` — world-0 parity err 131 rad (run 2 also tripped the
throughput gate); `tiny_timestep`/`short_settle` — physics-oracle read-backs
(arm err 1.18 / 0.41 rad); the three structure mutants died before any sim
ran.

## Deviations

- The builder sandbox has no GPU, so `judge/selftest.sh` ran in cpu-check
  mode: the two gpu-tagged mutants (`low_capacity`, `over_ladder`) were
  skipped there and killed for real on the GPU leases (8/8 both runs).
- `run.py --gpu` does not run `judge/setup.sh` on the lease — the slice image
  already ships the pinned toolchain (verified by the engine-parity gate:
  GPU-reported mujoco 3.8.1 == CPU-measured 3.8.1). `setup.sh`/`selftest.sh`
  were exercised locally instead, above.
- CPU steps/s varies with lease contention (24.2k vs 33.6k); the throughput
  gate is a ratio against the same run's CPU baseline, so both runs cleared
  the ×4 floor by a wide margin.
- The parity error is byte-identical across runs (0.008110745441113454 rad):
  the sim itself is deterministic; only wall-clock and throughput numbers
  move. They live under `timing` in the verdict, which the determinism check
  excludes.
- No `media/`: the judge produces verdict JSON only; the measured table above
  is the demo's figure. (SPEC: media is generated "when present".)
- `REPRODUCE.md` is left for the independent-reproduction pass by a different
  agent before merge, per `cookbook/DEMO-STANDARD.md`.
