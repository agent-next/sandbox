# gpu-sim-sweep: CPU-for-one-world, GPU-for-thousands — SPEC

An agent works inside a disposable sandbox on a real GPU-simulation problem:
configure a MuJoCo-Warp scene (an arm + 8 falling boxes on a table), sweep it
over nworld = 1..8192 on a 4 GiB RTX 5090 slice, and pass a judge that
re-runs the physics itself and never trusts a number the artifact claims.

## Goal

- Artifact: a sim config file (`sweep.json`) — physics parameters and the
  nworld ladder. Nothing else: the artifact is an *input*, not a report.
- Judge: `judge/grade.sh` runs the simulation it gates on — a CPU mujoco
  baseline plus the mujoco_warp sweep — and applies numeric, deterministic
  pass rules to what it measures. Runnable on GPU machines (full path) and
  CPU-only machines (`--cpu-check`).
- Self-test: `judge/selftest.sh` proves the judge fails known-bad configs,
  with the kill rate coming from real runs.

## Non-goals

- Beating a specific speedup target (throughput is measured and gated
  against a floor, but physics correctness is the heart of the demo).
- Multi-GPU work, rendering, real robot control, network access on the GPU
  lease.

## The artifact contract

`sweep.json` is CONFIG ONLY. It must define exactly:

| key | what |
|---|---|
| `scene` | MJCF XML string; must equal the canonical scene after whitespace normalisation |
| `timestep` | physics timestep in seconds, in (0, 0.01] (e.g. 0.001) |
| `solver_iterations` | solver iterations per step (e.g. 100) |
| `nconmax` | max contacts per world (e.g. 64) |
| `njmax` | max constraint rows per world (e.g. 256) |
| `nworld_ladder` | list of ≥ 2 world counts to sweep (e.g. [1, 64, 512, 2048, 8192]) |
| `settle_steps` | steps to settle before the oracle read-back (e.g. 800) |
| `timed_steps` | steps timed per batch (e.g. 200) |
| `batches` | number of timing batches (e.g. 2) |
| `notes` | optional free-text string |

Any other key is rejected; keys that smuggle results (`points`,
`cpu_steps_per_s`, `cpu_mujoco_version`, trajectories, anything result-
shaped) are called out by name. **The judge computes every number it gates
on by running the simulation itself during grade.** The artifact's claims
about results are never read — there is nothing to read.

The judge builds the effective XML by patching the canonical scene's
`<option>` element with the config's `timestep` and `solver_iterations`, and
passes `nconmax`/`njmax` to `mujoco_warp.put_data`. `settle_steps`,
`timed_steps` and `batches` drive the measured runs.

## Judge gates (numeric pass rules)

`judge/grade.sh <artifact> [--seed N] [--json out.json] [--cpu-check]
[--speedup-floor F]` exits 0 only if every gate in its mode passes. Modes:
auto — full when a CUDA device is available (`warp.is_cuda_available()`),
otherwise cpu-check; `--cpu-check` forces the CPU path. The artifact is
graded from a copy in a temp dir; sha256 checksums of `judge/` before and
after must match (`judge_intact`). A judge crash exits 2, distinct from
rc=1 "graded and failed".

**Full mode** (measured by the judge on the GPU lease / GPU machine):

1. **structure** — valid JSON, ≤ 256 KiB, exactly the contract keys with
   correct types, no result keys, scene XML equals canonical.
2. **engine-parity** — the mujoco version measured on the GPU sweep equals
   the version measured by the CPU baseline.
3. **physics-oracle** — every nworld in the ladder must run and its live
   read-back must satisfy: qpos/qvel finite; arm tracking error < 0.15 rad;
   box min z > table_top − 0.02 (no tunnelling); box max z <
   table_top + 0.25 (landed); box speed max < 5.0 m/s (energy bounded);
   confirmed world count == nworld. A point that fails to allocate counts
   as an observed failure, not a crash.
4. **cpu-parity** — measured GPU world-0 qpos trajectory vs the measured
   CPU trajectory, max abs error ≤ 0.05 rad over the settle window. (The
   two engines diverge ~8e-3 rad over 800 steps — float32 accumulation;
   mutants diverge by ≥ 0.1 or explode.)
5. **throughput** — measured top-nworld aggregate steps/s ≥ floor ×
   measured CPU steps/s (default floor 4×; measured ~12–31× on the 4 GiB
   lease). Reported in the verdict as `top_steps_per_s`,
   `cpu_steps_per_s`, `speedup`.

**cpu-check mode** (no GPU): gate 1 plus **cpu-physics** — the same live
oracle (finite, landed, bounded, arm converged) applied to the judge's CPU
reference run of the artifact's config. GPU-only failures (contact
capacity, slice OOM) are not observable here.

## Acceptance oracle

Correctness is decided by: CPU `mujoco.mj_step` as the reference tool, a
measured CPU-vs-GPU world-0 trajectory comparison, a physics oracle read
from live sim state at every ladder point, and real throughput measurement.
An artifact that merely "runs" without matching the oracles fails; an
artifact that *reports* results is rejected unread.

## Known-bad examples (self-test)

`judge/mutants.py` derives known-bad configs from the known-good one by
scripted single edits and tags each with the minimum mode that can observe
its failure:

| mutant | edit | observed kill |
|---|---|---|
| smuggled_results | adds `points`/`cpu_steps_per_s`/`cpu_mujoco_version` | structure (result keys) — cpu |
| gravity_flipped | `gravity="0 0 -9.81"` → `+9.81` in scene | structure (scene != canonical) — cpu |
| missing_nconmax | deletes `nconmax` | structure — cpu |
| tiny_timestep | `timestep` 0.001 → 0.0001 | boxes still falling at read-back — cpu |
| short_settle | `settle_steps` 800 → 20 | arm unconverged, boxes mid-air — cpu |
| solver_iter_1 | `solver_iterations` 100 → 1 | CPU contact solver explodes (box speed > 17000 m/s); GPU diverges — cpu-physics / cpu-parity |
| low_capacity | `nconmax`/`njmax` → 8/32 | observed tunnelling (box z → −2.4) once boxes land — gpu |
| over_ladder | ladder + 65536 | observed clean OOM at put_data — gpu |

`judge/selftest.sh` grades the known-good (must pass) in auto mode, then
every mutant its mode can observe (each must fail ≥ 1 gate; gpu-tagged
mutants are skipped in cpu-check mode), prints the kill rate, and checks
determinism. It exits non-zero unless the attempted kill rate is ≥ 90 %.
(dt=0.01 was measured *stable* under implicitfast, so the timestep mutant
shrinks dt instead — the settle window can no longer land the boxes.)

## Toolchain (pinned, sha256-checked)

`judge/setup.sh` installs into `$HOME/.venvs/gpu-sim-sweep/` exactly what the
judge needs: mujoco 3.8.1, mujoco-warp 3.8.1, warp-lang 1.13.0, numpy 1.26.4
and the transitive closure, every wheel pinned and sha256-verified through
pip's `--require-hashes` mode (`judge/requirements.lock`, CPython 3.10–3.13
x86-64 Linux; every pinned release predates 2026-09-30). `setup.sh` is
idempotent and writes `judge/VERSIONS.txt` with what it actually installed.

## Reproducibility

Grading is deterministic given `--seed`: two grades produce byte-identical
verdict JSON except the `timing` key (all measured numbers and wall-clock
values live there) — enforced by `selftest.sh`. RECEIPT.md carries real
pasted output of setup, selftest and grade with exit codes, kill rate, key
numbers and wall times, plus a Deviations section. Media under `media/` is
generated from committed run data by `media/make_media.sh` when present;
the judge itself produces no media.

## GPU path (lead's run, 2026-10-14)

The GPU path uses a 4 GiB VRAM slice lease created via the agent-next REST API:

```
POST /sandboxes {"accel":{"vram_gb":4,"reserve":"exec"}}
→ returns lease id (gl-...)
POST /sandboxes/{id}/exec {"code": <python>, "timeout_s": 2400}
→ unpacks judge/ + examples/, grades the good config and every mutant:
   each grade runs the CPU baseline + the mujoco_warp sweep itself
DELETE /sandboxes/{id}
GET /sandboxes/{id} → 404 (or phase=dead)
```

The lease image already has Python 3.13, mujoco 3.8.1, mujoco-warp 3.8.1,
warp-lang 1.13.0, numpy 1.26.4 on an RTX 5090 slice (cc 12.0); no pip
needed. Warp kernels cold-compile ~60–100 s per fresh lease (measured;
reported as setup time under `timing.cold_compile_s`, not sim time), then
run warm from the kernel cache.
