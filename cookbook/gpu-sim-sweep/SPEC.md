# gpu-sim-sweep: CPU-for-one-world, GPU-for-thousands — SPEC

An agent works inside a disposable sandbox on a real GPU-simulation problem:
configure a MuJoCo-Warp scene (an arm + 8 falling boxes on a table), sweep it
over nworld = 1..8192 on a 4 GiB RTX 5090 slice, verify the physics at every
point against a CPU baseline, and produce a throughput curve with the speedup
over CPU reported honestly. The judge never accepts "it ran": it re-runs the
same physics on CPU, compares trajectories, checks the oracle at every sweep
point, and gates the throughput claim.

## Goal

- Artifact: a sim config file (`sweep.json`) with the scene XML, physics
  parameters, nconmax/njmax contact capacity, and nworld ladder.
- Judge: `judge/grade.sh` with numeric, deterministic pass rules, runnable on
  GPU machines (full path) and CPU-only machines (`--cpu-check`).
- Self-test: `judge/selftest.sh` proves the judge fails known-bad configs.

## Non-goals

- Beating a specific speedup target (throughput is measured and reported; a
  floor can be requested with `--speedup-floor` but physics correctness is the
  only default gate).
- Multi-GPU work, rendering, real robot control, network access on the GPU
  lease.
- Verifying GPU performance on a CPU-only machine; the GPU throughput path
  needs a CUDA sandbox.

## The artifact contract

`sweep.json` must define:

| key | what |
|---|---|
| `scene` | MJCF XML string (arm + boxes scene) |
| `timestep` | physics timestep in seconds (e.g. 0.001) |
| `solver_iterations` | solver iterations per step (e.g. 100) |
| `nconmax` | max contacts per world (e.g. 64) |
| `njmax` | max constraints per world (e.g. 256) |
| `nworld_ladder` | list of world counts to sweep (e.g. [1, 64, 512, 2048, 8192]) |
| `settle_steps` | steps to settle before timing (e.g. 800) |
| `timed_steps` | steps to time per batch (e.g. 200) |
| `batches` | number of timing batches (e.g. 2) |
| `cpu_steps_per_s` | measured single-world CPU throughput |
| `cpu_mujoco_version` | mujoco version on CPU |
| `points` | list of per-nworld results (nworld, steps_per_s, oracle flags) |

- The judge calls the CPU reference on the same XML, runs the GPU sweep on
  the same XML, and compares.
- The artifact must not contain paths, hostnames, or keys from a specific
  machine. The judge rejects an artifact whose scene differs from canonical
  (after whitespace normalization), so only the numeric parameters are
  tunable.

## Judge gates (numeric pass rules)

`judge/grade.sh <artifact> [--seed N] [--json out.json] [--cpu-check]
[--speedup-floor F]` exits 0 only if gates 1–5 all pass. `--seed` (default 0)
offsets case seeds. Modes: auto — full mode when a GPU is available,
otherwise cpu-check; `--cpu-check` forces the CPU path. The artifact is
graded from a copy in a temp dir; sha256 checksums of `judge/` before and
after must match.

1. **structure** — the artifact is valid JSON, ≤ 256 KiB, defines all required
   keys with correct types, and the scene XML normalises to the canonical
   scene.
2. **engine-parity** — the mujoco version reported by the GPU sweep equals
   the CPU baseline's version.
3. **physics-oracle** — for every nworld in the ladder:
   - qpos/qvel are finite everywhere (no NaN/inf);
   - arm tracking error < 0.15 rad;
   - box min z > table_top - 0.02 (no tunnelling);
   - box max z < table_top + 0.25 (boxes landed);
   - box speed max < 5.0 m/s (energy bounded);
   - world count confirmed == nworld.
4. **cpu-parity** — GPU world-0 qpos trajectory matches the CPU trajectory
   within tolerance: max abs error ≤ 1e-3 (rad) per joint over the settle
   window.
5. **throughput** — the top ladder point's aggregate steps/s ≥ the floor
   (default: 20x CPU baseline). Reported in the verdict JSON as
   `top_steps_per_s`, `cpu_steps_per_s`, and `speedup`.

cpu-check mode skips gates 2–5 (no GPU available) and passes gate 1 only.

## Acceptance oracle

The judge never trusts the artifact's own idea of correct. Correctness is
decided by: CPU mujoco mj_step as the reference tool, trajectory comparison
(CPU vs GPU world-0), the physics oracle (finite, bounded, landed), and a
real GPU compilation of the sweep. An artifact that merely "runs" without
matching the oracles fails.

## Known-bad examples (self-test)

`judge/mutants.py` derives ≥ 6 known-bad artifacts from the known-good one by
scripted single edits: default nconmax/njmax (the headline bug — contacts
silently dropped at nworld ≥ 2048), timestep ×10 (blow-up), solver iterations
= 1 (incomplete convergence), gravity sign flipped (boxes fly), wrong nworld
capacity per slice (OOM must be reported as a clean fail), and a NaN injection.
`judge/selftest.sh` grades the known-good (must pass) and every mutant (each
must fail ≥ 1 gate), prints the kill rate, and checks determinism. It exits
non-zero unless the kill rate is ≥ 90 %.

## Toolchain (pinned, sha256-checked)

`judge/setup.sh` installs into `$HOME/.venvs/gpu-sim-sweep/` exactly what the
judge needs: mujoco 3.8.1, mujoco-warp 3.8.1, warp-lang 1.13.0, numpy 1.26.4
and the full transitive closure, every package pinned and sha256-verified
through pip's `--require-hashes` mode. A lock file, generated by
`judge/genlock.py` from live PyPI hashes, pins one URL + sha256 per wheel
per supported CPython. Wheels are covered for CPython 3.10–3.13 on x86-64
Linux. Every pinned release predates 2026-09-30. `setup.sh` is idempotent.
`judge/VERSIONS.txt` records what it actually installed.

## Reproducibility

Grading is deterministic given `--seed`: two runs produce byte-identical
verdict JSON except the `timing` key (CUDA timing is inherently noisy) —
enforced by `selftest.sh`. RECEIPT.md carries real pasted output of setup,
selftest and grade with exit codes, kill rate, key numbers and wall time of
each, plus a Deviations section. Demo media under `media/` is generated from
committed run data by `media/make_media.sh`; the judge itself produces no
media.

## GPU path (lead's run, 2026-10-14)

The GPU path uses a 4 GiB VRAM slice lease created via the agent-next REST API:

```
POST /sandboxes {"accel":{"vram_gb":4,"reserve":"exec"}}
→ returns lease id (gl-...)
POST /sandboxes/{id}/exec {"code": <python>, "timeout_s": 600}
→ runs the full judge: structure + CPU reference + GPU sweep + oracle
DELETE /sandboxes/{id}
GET /sandboxes/{id} → 404 (or phase=dead)
```

The lease image already has Python 3.13, mujoco 3.8.1, mujoco-warp 3.8.1,
warp-lang 1.13.0, numpy 1.26.4 on an RTX 5090 slice (cc 12.0); no pip needed.
Warp kernels cold-compile ~25 s per fresh lease; report it as setup time.
