# SPEC: Real2Sim from a reference rollout

## Goal

An agent is shown **a reference rollout of a RoboSimStudio scene** — a rendered
video plus the per-frame particle positions of a towel being folded — that was
produced with **hidden material parameters**. It is given the scene file, the
list of editable parameters with units and ranges, and `judge/grade.sh` for
feedback. It must produce a `params.json` that makes the *same* scene reproduce
the reference motion.

This is the paper's agentic Real2Sim loop (Sec. 3 "Iterative Interface for
Agents", Sec. 4.1, Fig. 4) reduced to the part a sandbox can decide: the agent
edits scene parameters, runs, reads simulator-state feedback, and refines until
the simulation matches observed behaviour. Fig. 4 is the same towel under four
bending/stretch stiffness choices; here three of the four are mutants.

## Non-goals

Out of scope and stated as such in README limits, because none of it runs on a
Python 3.13 GPU slice with no network:

- the real robot, the smartphone video, and force-feedback teleoperation (the
  Gello leader arm);
- Graph-as-Policy training (`robosimstudio_policy_agent`, needs torch + cuRobo);
- the SuperDex sponge (`wipe_the_bar`) — `superdex-physics` publishes cp312
  wheels only;
- the OVRTX path tracer (`ovrtx`); rendering is Newton's `tiled` backend;
- recovering *robot* trajectory, which is given, not inferred. The agent
  recovers **material and contact parameters only**.

## The artifact

`params.json`, written by the agent:

```json
{
  "cloth": {"core_shear_modulus": 1.0e5, "tri_ke": 1.0e4, "core_damping": 1.0e-2},
  "contact": {"friction": 0.25, "contact_ke": 1.0e4},
  "shell": "slab"
}
```

Keys and units are exactly the ones RSS declares on `ClothMaterialSpec`
(`examples/01_cloth/cloth.py`), whose `ui(...)` metadata is the authority for
the ranges below — not invented here. `shell` is the one discrete choice
(`"slab"` or `"membrane"`).

## Gates

All five are numeric and seeded. `grade.sh` prints one JSON verdict and exits 0
only if every gate passes.

### G1 — params inside documented ranges

Every key in `params.json` must name a real `ClothMaterialSpec` field and its
value must lie in that field's declared range. Unknown keys are rejected, not
ignored. Log-scaled fields are compared in log space, because a range of
`1.0e3 … 1.0e7` is four decades and a linear tolerance would be meaningless.

| field | unit | range | scale |
| --- | --- | --- | --- |
| `tri_ke` | N/m | 1.0e2 … 1.0e6 | log |
| `tri_ka` | N/m | 1.0e2 … 1.0e6 | log |
| `tri_kd` | N·s/m | 1.0e-4 … 1.0e0 | log |
| `edge_ke` | N·m/rad | 1.0e-5 … 1.0e2 | log |
| `edge_kd` | N·m·s/rad | 1.0e-6 … 1.0e-1 | log |
| `core_shear_modulus` | Pa | 1.0e3 … 1.0e7 | log |
| `core_lame_lambda` | Pa | 0.0 … 1.0e7 | linear |
| `core_damping` | Pa·s | 1.0e-4 … 1.0e1 | log |
| `areal_density` | kg/m² | 0.05 … 1.5 | linear |
| `thickness` | m | 0.0 … 0.02 | linear |
| `particle_radius` | m | 2.0e-4 … 1.0e-2 | log |
| `contact_ke` | N/m | 1.0e2 … 1.0e6 | log |
| `contact_kd` | N·s/m | 1.0e-3 … 1.0e2 | log |
| `friction` | – | 0.0 … 1.0 | linear |

### G2 — trajectory match on the training motion

Re-simulate the scene with the agent's params on the **training** arm track
(the one whose reference video the agent was shown), and compare per-frame
particle positions against the reference:

```
e = mean over frames t and particles i of || q_sim[t, i] - q_ref[t, i] ||   [m]
```

`G2` passes when `e <= 3 * e_truth`, where `e_truth` is the same error for the
**hidden** parameters re-run under a **different perturbation seed**. That
calibration is done by `judge/make_reference.py` and written to
`judge/thresholds.json`; it is the difference between "it ran" and "it matches".

### G3 — held-out motion

The same comparison on a **different arm track** the agent never saw: a
different approach path and a different fold direction, same hidden params.
`G3` passes when `e_heldout <= 3 * e_truth_heldout`. This is the gate that
kills a params.json fitted to the one rollout it was shown.

### G4 — task outcome

RSS's own task scorer (`robosimstudio_bench`, `06_tasks`) reports the task's
outcome for the reference and for the agent's rollout. The **outcome class**
must match (e.g. both "folded" or both "not folded"), and the scalar reward must
be within the tolerance `judge/thresholds.json` records. A rollout that matches
positions but ends in a different task state does not pass.

### G5 — sim health

- every particle position and velocity finite at every recorded frame;
- no particle farther than `judge/thresholds.json`'s `explosion_radius` from the
  scene origin (a stiff or unstable parameter set blows up rather than drifts);
- contact count within the band recorded for the reference (a set that produces
  an order of magnitude more contacts is colliding with itself).

## The acceptance oracle

The judge holds the hidden truth: `judge/make_reference.py` draws the hidden
params from a fixed seed, simulates both tracks, and writes the reference
rollout, the video, and `judge/thresholds.json`. **The hidden params live only
in the judge.** The agent sees the video, the positions, the scene file and the
ranges above.

## Mutants

`judge/mutants.py` generates single-edit mutants of the good `params.json`.
Required set (≥ 6):

| mutant | edit | expected to fail |
| --- | --- | --- |
| `stiff_x10` | `core_shear_modulus *= 10` | G2, G3 |
| `stiff_div10` | `core_shear_modulus /= 10` | G2, G3 |
| `stretch_x100` | `tri_ke *= 100` | G2, G3 |
| `friction_zero` | `friction = 0.0` | G4 (and G2) |
| `damping_huge` | `core_damping *= 1000` | G2, G3 |
| `wrong_shell` | `shell = "membrane"` | G2, G3 |
| `constraint_fixed` | the paper's Sec. 4.3 mutant: a body that is free in the good artifact is pinned | G4 |

Kill rate must be ≥ 90 %: every mutant fails at least one gate. The good
artifact passes all five.

## Determinism

Every random choice takes `--seed`. Solvers run with fixed thread counts where
results depend on it. `grade.sh` twice with the same seed gives byte-identical
verdict JSON except under the `timing` key, which `selftest.sh` checks.
