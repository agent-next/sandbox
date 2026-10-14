# SPEC — rf-openems: 2.45 GHz RF/EM demo on disposable sandboxes

## Goal

An agent can design and verify a **2.45 GHz microstrip patch antenna on FR-4**
with a full-wave 3-D FDTD solver inside a disposable agent-next sandbox, and a
judge it cannot fool decides whether the design works. The deliverable is a
parameterised Python model script; the judge runs the simulation itself and
checks the result against numeric gates plus an independent analytic oracle.

## Deviation from the brief (recorded up front)

The brief asks for **openEMS**. openEMS is not available through any pinnable
channel usable in this sandbox: it is absent from PyPI (`pip index versions
openEMS → no matching distribution`), absent from conda-forge
(`repodata.json` has no `openems-*` artifacts), absent from Debian bookworm,
and upstream (bismuth.dev/openEMS) has hosted no binary release tarballs since
2019 — building from source is the only route and cannot be pinned to a
sha256-checked tarball with a reproducible build inside minutes. The judge
**therefore uses MEEP (pymeep 1.31.0 from conda-forge, pinned + sha256/record
checked)** instead — same physics (3-D cartesian FDTD), same deliverable type
(parameterised simulation script), same oracle class. This is recorded in
`RECEIPT.md` and `DEVIATIONS.md`.

## Non-goals

- Optimising gain / efficiency / pattern — only the driving-point (S11) gate
  counts. (Far-field radiation is optional / disabled at default resolution;
  an off-by-default gate is not part of grading.)
- Broadband design (fidelity 2.0–2.9 GHz is enough).
- Antenna array / feeding networks.
- Production-grade mesh convergence study (we require one coarse→fine
  *confirmation run*, documented — not an asymptotic Richardson study).

## The artifact

`antenna.py` — a Python script the user/agent produces, with these **public
parameters in a top-of-file block** (must exist, be assignable, and be in
mm/GHz units as named):

```
f_target_g   = 2.45    # GHz
suburb_er = 4.4        # substrate permittivity, FR-4
patch_L = 30          # mm — patch length along propagation
patch_W = 37          # mm
substrate_h = 1.6     # mm
feed_inset = 3        # mm from patch edge (front)
side_gnd_gap = 5      # mm clearance patch↔edge of outer ground ring
resolution = 10       # voxel cells / mm (mesh)
```

The script must emit, to stdout, exactly one line:
`RESULT S11_dB_at_<f_target> <f_res_GHz> <f_res_within_pct>`
where the two resonance checks come from the script’s own frequency sweep
(displayed by the judge; the judge re-derives them independently from the
data written by the sim to an artifact-local JSON: `antenna_results.json`).

The script must produce `antenna_results.json` next to itself:
`{"S11_dB_at_target": x, "f_res_GHz": y, "freqs_GHz": [...], "S11_dB": [...]}`
so the judge can cross-plot.

## Judge gates (all must pass — exit 0 only then)

| # | gate | rule |
|---|---|---|
| G1 | artifact sanity | `antenna.py` parses (py_compile), contains the 9 parameters, each within 3× of good value — catches degenerate files |
| G2 | physical sanity | substrate thickness ∈ [0.5, 2.5] mm; patch L ∈ [20, 45] mm; er ∈ [3.5, 5.0]; resolution ∈ [6, 18] |
| G3 | sim runs clean | judge executes the artifact under a 9-min wall limit; results JSON valid, freqs span 2.2–2.7 GHz with ≥ 21 points |
| G4 | S11 target | `S11_dB_at_target ≤ −10.0 dB` (at 2.45 GHz) |
| G5 | resonance location | `f_res_GHz` (minimum |S11| in band) within ±2 % of 2.45 GHz |
| G6 | **analytic oracle** | independent Hammerstad-Jensen 50 Ω microstrip line at 1.6 mm FR-4 → within 3 % of MEEP-derived characteristic impedance (same mesh/substrate); also patch-length quasi-static estimate within ±10 % of best-fit — printed for the human; fail if > 3 % |
| G7 | convergence | the judge re-runs the sim at `resolution+2` and requires `ΔS11_dB ≤ 1.0 dB` at target — catched coarse-mesh flukes |
| G8 | judge integrity | sha256 of `judge/` tree before & after the run must match |

## Acceptance oracle

- **Hammerstad–Jensen closed-form Z₀** for a 50 Ω microstrip on FR-4 (W/h =
  1.965, er = 4.4, h = 1.6 mm), run as a separate MEEP *verification* sim and
  computed in pure Python.
- **Patch resonance quasi-static**: f_r ≈ c / (2·L·√εeff) within ±10 % of
  MEEP.
- **Self-test**: 6 scripted single-edit mutants (known-bad substrate, wrong
  patch length, missing ground plane, missing feed inset, resolution too
  coarse, NaN-poisoned `er`) all fail at least one gate; kill rate must be
  ≥ 90 %.

## Provenance

MEEP is MIT-licensed (github.com/NanoComp/meep; 1.31.0 wheels shipped from
conda-forge). The patch-antenna geometry equations are standard literature
(Balanis, *Antenna Theory*; Pozar, *Microwave Engineering*). My simulator
script is written from scratch; no third-party code is imported other than
MEEP + numpy.
