# gpu-sim-sweep — independent reproduction

Recorded on 2026-10-15 by GLM-5.3 (GLM model family), **not the builder**. I
followed only `cookbook/gpu-sim-sweep/README.md` as an outsider would, running
its documented commands unchanged from the repository root. I read
`run.py` (the documented one-command run) but no judge source; `SPEC.md` was
read for the stated tolerances and `RECEIPT.md` for the comparison numbers,
since this report must compare against them.

Environment: Python 3.12.3; Linux x86-64; `sbx` CLI 0.0.1. The lease
reported Python 3.13.5.

The demo is not on `main` yet (it arrives with its PR), so the README's
documented ref override was **required**, not merely optional, for the CPU
path: both commands below use `--ref sbx/sweep-r5`. Per the README, `--ref`
selects the cloned branch on the CPU-sandbox path only; on the GPU path
`run.py` packs the local checkout's `judge/` + `examples/`, so the flag is a
no-op there. It was passed on both commands anyway, unchanged from the
documented form. This reproduces the packaged demo, not a newly written
simulation. The local-judge alternative (`judge/setup.sh` on my machine) and
the interactive "Ask your agent" workflow were not exercised; the CPU path
below ran `setup.sh`, `selftest.sh` and `grade.sh` inside the sandbox, as the
one-command run does.

## Run 1 — CPU path (README one-command run, documented ref override)

| command | exit | wall | key numbers |
|---|---|---|---|
| `python3 cookbook/gpu-sim-sweep/run.py --ref sbx/sweep-r5` | 0 | 178 s | setup ok; selftest kill rate 6/6 = 100 % (2 gpu-only skipped), determinism OK; grade PASS (mode cpu-check); CPU oracle arm err 0.06069678799920897 rad, box z [0.31499750273463084, 0.3149975027350041] m, box speed 2.8909458160697454e-11 m/s |

```text
  [create] sbx create --timeout-min ... ok (1 s)
sandbox: 01a14014-69a7-79b1-86ff-4747fbcd8564 (template default)
  [clone] sbx exec 01a14014-69a7-79b1-86ff-4747fbcd8564 ... ok (8 s)
setup.sh: creating venv at /home/user/.venvs/gpu-sim-sweep
Collecting mujoco==3.8.1 ...
Collecting warp-lang==1.13.0 ...
Successfully installed absl-py-2.5.1 etils-1.14.0 fsspec-2026.9.0 glfw-2.10.2
mujoco-3.8.1 mujoco-warp-3.8.1 numpy-1.26.4 pyopengl-3.1.10
typing-extensions-4.16.0 warp-lang-1.13.0 zipp-4.1.1
setup.sh: ok
  [setup] sbx exec 01a14014-69a7-79b1-86ff-4747fbcd8564 ... ok (113 s)
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
selftest: determinism: OK
selftest: ok
  [selftest] sbx exec 01a14014-69a7-79b1-86ff-4747fbcd8564 ... ok (39 s)
  [grade] sbx exec 01a14014-69a7-79b1-86ff-4747fbcd8564 ... ok (12 s)
  [kill] sbx kill 01a14014-69a7-79b1-86ff-4747fbcd8564 ... ok (2 s)
cleanup: sandbox 01a14014-69a7-79b1-86ff-4747fbcd8564 killed and confirmed gone
total: 178 s

gpu-sim-sweep demo: PASS (mode cpu-check)
  gate cost: pass
  gate cpu-physics: pass
  gate structure: pass
[exit_code=0]
```

The full verdict JSON (seed 0, `judge_intact: true`, mode cpu-check) reports
`mujoco_version 3.8.1`, `arm_max_err 0.06069678799920897`,
`box_z_min 0.31499750273463084`, `box_z_max 0.3149975027350041`,
`box_speed_max 2.8909458160697454e-11` — byte-identical to the CPU oracle
values recorded in RECEIPT.md's acceptance run, and a measured CPU 5,475
steps/s on the CPU sandbox template (not gated in cpu-check mode; the
RECEIPT's 26.6k–35.7k CPU baselines were measured on the GPU lease's CPU,
a different machine).

## Run 2 — GPU path (README one-command run, documented ref override)

The first invocation could not create a lease at all (HTTP 409, no free
seat on the GPU node — the node was holding other tenants' leases, which I
left untouched) and one later attempt met a platform-wide "node unreachable"
window mid-run. Neither is a demo defect; both are the repeat-and-cleanup
situations RECEIPT.md's Deviations section already documents. I repeated the
**same documented command** until one attempt ran to completion:

### Attempt A — no seat

| command | exit | key event |
|---|---|---|
| `python3 cookbook/gpu-sim-sweep/run.py --gpu --ref sbx/sweep-r5` | 1 | `POST /sandboxes: HTTP 409 ... no GPU node has a free seat` — no lease created, nothing to clean up |

### Attempt B — lease gl-0626f0-5: dropped exec reply (designed failure path)

| command | exit | key event |
|---|---|---|
| same | 1 | grade-good exec reply dropped after 181 s (`RemoteDisconnected`); run.py's single retry got HTTP 409 "lease already has a job in flight" (the grade was still running server-side); run.py destroyed the lease and confirmed it gone |

```text
created gl-0626f0-5 (4 GiB VRAM slice)
  [unpack] exec ok (1 s)
lease python 3.13.5; 8 mutants generated
  [grade good] exec transport error after 181 s: RemoteDisconnected: Remote end
closed connection without response; retrying once
run.py: POST /sandboxes/gl-0626f0-5/exec: HTTP 409: {"code":409,"message":"lease gl-0626f0-5 already has a job in flight"}
destroying gl-0626f0-5...
destroyed gl-0626f0-5; verified absent or dead
```

### Attempt C — lease gl-0626f0-6: platform outage mid-run

| command | exit | key event |
|---|---|---|
| same | 1 | unpack exec timed out during a gateway "node unreachable" window (HTTP 503s); cleanup could not be confirmed, and run.py failed loudly naming the id (its designed behaviour); I destroyed the lease manually |

```text
created gl-0626f0-6 (4 GiB VRAM slice)
  [unpack] exec transport error after 181 s: TimeoutError: The read operation timed out
...
run.py: cleanup unconfirmed for gl-0626f0-6: run sandbox_kill for this id
```

The lease survived the outage window, so I destroyed it myself with
`sbx kill gl-0626f0-6`; a later GET returned 404 and `sbx list` excluded it.

### Attempt D — lease gl-0626f0-7: complete run (the reproduction)

| command | exit | wall | key numbers |
|---|---|---|---|
| `python3 cookbook/gpu-sim-sweep/run.py --gpu --ref sbx/sweep-r5` | 0 | 538 s | ladder 103 / 6,410 / 43,758 / 156,774 / 407,231 steps/s; CPU 22,639 steps/s; speedup ×18.0 (floor ×4.0); parity 0.008110745441113454 rad; cold compile 119.497 s; 8/8 mutants killed |

```text
created gl-0626f0-7 (4 GiB VRAM slice)
  [unpack] exec ok (1 s)
lease python 3.13.5; 8 mutants generated
  [grade good] exec ok (211 s)
  [grade smuggled_results] exec ok (1 s)
  [grade gravity_flipped] exec ok (1 s)
  [grade missing_nconmax] exec ok (0 s)
  [grade tiny_timestep] exec ok (0 s)
  [grade short_settle] exec ok (0 s)
  [grade solver_iter_1] exec ok (77 s)
  [grade low_capacity] exec ok (116 s)
  [grade over_ladder] exec ok (125 s)

gpu-sim-sweep demo: PASS (mode full)
  gate cost: pass
  gate cpu-parity: pass
  gate engine-parity: pass
  gate physics-oracle: pass
  gate structure: pass
  gate throughput: pass
  measured sweep (judge-ran, 4 GiB slice):
   nworld |     steps/s | arm err |            box z | 1st step s
        1 |         103 |   0.036 | [0.315,0.315] |     119.50
       64 |       6,410 |   0.036 | [0.315,0.315] |       0.01
      512 |      43,758 |   0.036 | [0.315,0.315] |       0.02
     2048 |     156,774 |   0.036 | [0.315,0.315] |       0.01
     8192 |     407,231 |   0.036 | [0.315,0.315] |       0.02
  CPU 22,639 steps/s, top GPU 407,231 steps/s (speedup x18.0, floor x4.0)
  cold Warp compile (first step): 119.497 s; parity max err 0.008110745441113454 rad

mutants: 8/8 killed
  gravity_flipped: FAIL (structure)
  low_capacity: FAIL (cpu-parity, physics-oracle)
  missing_nconmax: FAIL (structure)
  over_ladder: FAIL (physics-oracle, throughput)
  short_settle: FAIL (cost)
  smuggled_results: FAIL (structure)
  solver_iter_1: FAIL (cpu-parity)
  tiny_timestep: FAIL (cost)
destroying gl-0626f0-7...
destroyed gl-0626f0-7; verified absent or dead
total: 538 s
[exit_code=0]
```

## Comparison with RECEIPT.md and the README's acceptance run

| quantity | RECEIPT run 1 | RECEIPT run 2 | README acceptance run | reproduced | SPEC rule / result |
|---|---:|---:|---:|---:|---|
| verdict | PASS, exit 0, mode full | PASS, exit 0, mode full | PASS, exit 0, mode full | PASS, exit 0, mode full | all gates pass — **match** |
| mutants killed | 8/8 | 8/8 | 8/8 | 8/8 | ≥ 90 % — **match** |
| CPU↔GPU parity err | 0.008110745441113454 rad | same | same | 0.008110745441113454 rad | ≤ 0.05 rad — **byte-identical, match** |
| per-mutant failed gates | run-2 set | see list | run-2 set | identical to run 2 | every mutant fails ≥ 1 gate — **match** |
| speedup (floor ×4) | ×23.8 | ×15.6 | ×25.8 | ×18.0 | gate ≥ 4×; within builder spread ×15.6–25.8 — **match (gate)** |
| CPU baseline steps/s | 27,100 | 35,681 | 26,574 | 22,639 | contention-varied, not gated — **differs** |
| GPU nworld=1 | 206 | 122 | 134 | 103 | same — **differs** |
| GPU nworld=64 | 11,785 | 7,116 | 10,785 | 6,410 | same — **differs** |
| GPU nworld=512 | 80,685 | 60,842 | 77,008 | 43,758 | same — **differs** |
| GPU nworld=2048 | 275,739 | 222,929 | 248,064 | 156,774 | same — **differs** |
| GPU nworld=8192 | 645,390 | 557,066 | 686,725 | 407,231 | same — **differs** |
| arm tracking err | 0.036 rad | 0.036 rad | — | 0.036 rad, all points | < 0.15 rad — **match** |
| resting box z | 0.315 | 0.315 (min 0.314) | — | 0.315 at every point | landed, no tunnelling — **match** |
| engine parity | 3.8.1 == 3.8.1 | 3.8.1 == 3.8.1 | 3.8.1 == 3.8.1 | gate pass (mujoco 3.8.1) | versions equal — **match** |
| cold Warp compile | 86.3 s | 96.5 s | 104.945 s | 119.497 s | timing only — **differs** (above the README's quoted ~86–105 s band) |
| good-grade wall | 145 s | 163 s | 169 s | 211 s | timing only — **differs** |
| slowest mutant grade | 90 s | 84 s | — | 125 s | timing only — **differs** |
| end-to-end wall | 377 s | 390 s | 383 s | 538 s | timing only — **differs** |

What matches within the stated tolerances: every gated and deterministic
number. The parity error is byte-identical across all four runs (the sim is
deterministic; only timing moves, exactly as RECEIPT's Deviations section
says). The cpu-check grade's oracle values are byte-identical to the
RECEIPT acceptance run's CPU oracle (arm 0.06069678799920897 rad, box z
[0.31499750273463084, 0.3149975027350041] m, speed 2.8909458160697454e-11 m/s).
The self-test killed 6/6 observable mutants on the CPU path and 8/8 on the
GPU path, with the same per-mutant failed-gate sets as RECEIPT run 2. The
speedup ×18.0 clears the ×4 throughput floor and sits inside the builder's
measured ×15.6–25.8 spread. Toolchain matches everywhere: mujoco 3.8.1,
mujoco-warp 3.8.1, warp-lang 1.13.0, numpy 1.26.4, lease Python 3.13.5.

What differs: every wall-clock and throughput number, uniformly slower —
cold compile 119.497 s vs 86–105 s, good grade 211 s vs 145–169 s,
sim-running mutants up to 125 s vs "up to ~90 s", end-to-end 538 s vs the
README's "~6.5 min", and the whole ladder shifted down ~35 % below the
lowest builder run. The GPU node was busy with other tenants' leases during
my run; RECEIPT's own Deviations section documents exactly this contention
variance, and the throughput gate is a ratio against the same run's CPU
baseline, so the ×18.0 result is unaffected. Nothing was adjusted to force
matching timings.

## Cleanup verification

- CPU sandbox `01a14014-69a7-79b1-86ff-4747fbcd8564`: run.py killed it and
  confirmed via `sbx list`; my independent `sbx list` after the run also
  excluded it.
- GPU leases `gl-0626f0-5` and `gl-0626f0-7`: run.py printed DELETE followed
  by "verified absent or dead"; my independent GETs returned **HTTP 404**
  for both, and an independent `sbx list` excluded them.
- GPU lease `gl-0626f0-6` (abandoned during the platform outage): killed
  manually with `sbx kill`; GET now returns **HTTP 404** and `sbx list`
  excludes it.
- Leases belonging to other tenants were left untouched throughout.

## README frictions found

1. **The ref override is load-bearing until merge.** The headline commands
   without `--ref` clone `main`, which does not contain this demo. The
   documented "other ref" form (`--ref sbx/sweep-r5` here) was required for
   the CPU path; on the GPU path the flag is a documented no-op. A visitor
   reproducing before merge must know to add it.
2. **Timing ranges are optimistic under contention.** The README quotes
   ~86–105 s cold compile, ~145–169 s good grade, mutants "up to ~90 s", and
   ~6.5 min end-to-end; I measured 119.5 / 211 / 125 s and 9 min on a busy
   node. RECEIPT already notes throughput varies with lease contention, but
   a visitor may reasonably see numbers outside every quoted range while
   all gates still pass. Relatedly, SPEC.md's throughput note says
   "measured ×22.4–29.9" while RECEIPT run 2 measured ×15.6 and I measured
   ×18.0 — the SPEC's band understates the real spread.
3. **A dropped exec reply fails an otherwise-healthy run.** When the
   grade-good reply is lost, run.py's single retry can land on HTTP 409
   "lease already has a job in flight" (the grade is still running
   server-side) and abort, destroying the lease. This is the designed
   fail-loudly-and-repeat path — RECEIPT documents an equivalent mid-run
   death — but it means a successful GPU reproduction can take several
   attempts on a busy or flaky network.

## Verdict

**Gated and deterministic numbers match RECEIPT within the tolerances
stated in SPEC.md: YES.** The parity error is byte-identical
(0.008110745441113454 rad), the CPU oracle values are byte-identical, the
kill rates are 100 % on both paths with matching per-mutant gate outcomes,
the toolchain matches, and the measured ×18.0 speedup clears the ×4 floor
inside the builder's own spread. Every gate passes on both the CPU and GPU
paths, exit 0.

**Timing and throughput numbers differ: YES, uniformly slower** — cold
compile, per-grade walls and the whole steps/s ladder ran ~30–40 % slower on
a contended GPU node, consistent with (and covered by) RECEIPT's documented
contention variance; nothing about the physics or the judge moved.

**Unqualified headline-command reproduction: not until merge.** The
documented `--ref` override is required while the branch is unrebased; with
it, the demo reproduces exactly as advertised. No repository files other
than this report were edited. Scratch logs were deleted after the numbers
were recorded here.
