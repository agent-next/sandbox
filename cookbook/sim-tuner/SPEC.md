# sim-tuner / contract

## Goal and non-goals

Identify five parameters of a synthetic box-and-arm rig from six noisy
recordings. Produce `params.json`; the judge re-simulates it on four held-out
initial conditions and checks CPU/GPU numerical agreement. This is not
hardware system identification, a secure benchmark, model-structure learning,
or a GPU speed benchmark.

The scenario generator and source are public. “Hidden” means not passed to
the optimizer by the search tool, not inaccessible to a reader of this repo.
The shipped example fits **seed 7 only**. A new seed requires a new fit.

## Artifact

A UTF-8 JSON object, ≤ 16 KiB, with exactly these five finite numeric values.
Booleans, strings, duplicate keys, missing/extra keys, NaN and out-of-range
values are rejected. No clamping, artifact code or self-reported errors.

| parameter | inclusive range | meaning |
|---|---|---|
| `mu` | 0.15–0.90 | sliding friction coefficient |
| `solref_tc` | 0.005–0.020 | contact time constant, s |
| `solref_dr` | 0.80–1.60 | contact damping ratio |
| `damping` | 0.02–0.35 | hinge damping, N·m·s/rad |
| `armature` | 0.005–0.060 | hinge armature, kg·m² |

## Scenario and metric

`judge/engine.py` is authoritative for MJCF and metric. A 0.2 kg free box
slides and lands on a plane; a separate two-link arm tracks position commands
with `kp=60`. They do not touch. A recording is 500 steps at 2 ms (1 s),
with a command step after 250 steps. Sample after every fourth step:
125 observations of **seven** signals:
`box_x, box_z, box_zdot, q1, q2, q1dot, q2dot`.

The seed determines truth parameters within the table's ranges and ten
initial conditions, six training and four held-out. CPU MuJoCo generates
reference signals. Add seeded Gaussian noise with sigma = 1.5% of each
signal's training RMS. The same training scales normalize both splits.
Normalize `box_zdot` by the 95th percentile of its absolute noiseless training
values; normalize other channels by their training RMS. This prevents the
mostly-zero impact channel's small RMS from dominating the error.

The reported error is the root mean square of these scaled residuals over
all signals, samples and recordings. The judge computes candidate, default
and GPU scores itself. It never consumes errors from `params.json` or the
search history. Artifacts are copied to a temporary directory; judge source
hashes must remain unchanged.

## Gates

```bash
bash cookbook/sim-tuner/judge/grade.sh params.json --seed 7 --json verdict.json
```

| gate | numeric rule |
|---|---|
| G1 ranges | artifact satisfies the strict contract |
| G2 train | report CPU train error; no error threshold |
| G3 held-out | finite error `< 0.025` AND `< 0.30 × default held-out error` |
| G4 GPU/CPU | finite GPU train error; absolute difference `≤ 0.003` AND difference/CPU error `≤ 0.10`; pinned stack matches |

The binding oracle is the seeded CPU-generated noisy held-out recordings.
G4 is a numerical cross-check, not a second independent model of reality.
At seed 7 the accepted example measures held-out 0.022060 against default
0.118495 (fraction 0.1862). Those are real receipt values, not constants used
to compute the verdict. The thresholds are fixed, not learned from this
artifact at grade time.

Full grading needs a GPU lease. `--cpu-only` reports incomplete with G4
skipped, with exit 0 for successful CPU checks but JSON `pass: false`;
CPU gate success is not a full PASS. `--gpu-local` (or
`SIM_TUNER_GPU_LOCAL=1`) is for a process already inside the fresh GPU lease.
Otherwise grading creates its own 4 GiB lease and always deletes it, including
on evaluation exceptions. Cleanup must be confirmed, not inferred from DELETE.

## Self-test

`judge/selftest.sh` requires the known-good example to pass full grading.
Eighteen scripted negative controls must each fail an actual CPU gate:

- ten single-parameter range-edge mutations;
- defaults, a 6%-of-range truth shift and a deterministic biased fit;
- swapped units, extra key, NaN, string and out-of-range value.

The biased fit is deliberately biased, **not** an optimizer proven to overfit
training noise. Infrastructure failures are errors, never mutant kills.
Every shipped mutant must be killed; a summary ≥ 90% is not permission to
ignore a survivor. Two CPU-path grades must match excluding timing; GPU
agreement is checked against the numeric tolerances above.

## Pinned tools

CPU setup: Linux x86-64, Python 3.10–3.13, MuJoCo 3.8.1, NumPy 1.26.4
(Python 3.10–3.12) or 2.1.3 (Python 3.13), full transitive hashes in
`judge/requirements.lock`. `judge/VERSIONS.txt` records the reference stack.
Media adds Pillow 11.3.0. No plotting dependency is used.

GPU: `judge/version-table.json`, including MuJoCo 3.8.1, mujoco-warp 3.8.1,
warp-lang 1.13.0, Python 3.13.5 and NumPy 1.26.4. This lease image is
validated rather than installed; the image's NumPy build differs from the
public cp313 wheel pin. Stack drift fails validation. Buffer limits are
`nconmax=16`, `njmax=72`; one world per candidate × recording, ≤ 1024 worlds
per chunk.

## Reproduction and media

Two fresh lease runs are pasted in `RECEIPT.md`. Same-seed CPU numbers should
match at the six decimals printed by the judge; GPU agreement must satisfy
G4, not a timing tolerance. The one-command path uploads this checkout,
does not fetch moving sources, and always verifies lease destruction.
Independent reproduction is a separate later gate.

`media/collect.py` captures all 501 qpos/qvel states inside actual CPU
scoring, then requires G1–G3 to equal the accepted lease report.
Default, tuned and noiseless truth use the same model, initial state,
timestep and command. Rendering adds only lights, textures and a
non-colliding zero-mass mount. Every displayed state is selected from that
captured array without interpolation and checked within 1e-9.
The 25 s video is 1080p30; repeated real-time replay is labelled.
