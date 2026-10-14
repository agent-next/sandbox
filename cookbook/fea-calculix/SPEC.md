# FEA cantilever beam sizing with CalculiX — spec

## Goal

Size a rectangular steel cantilever beam for a fixed tip load so that

- the maximum von Mises stress stays below the allowable stress, and
- the tip deflection stays below the deflection limit,

while keeping the mass small. The agent produces the geometry and the
CalculiX deck; the judge meshes it with gmsh, runs `ccx`, and checks the
result against an Euler-Bernoulli oracle — never just "the solver ran".

## Fixed problem statement (judge constants)

| quantity | value |
|---|---|
| tip load P | 1000 N, applied in −Z, split equally over the 4 tip corner nodes |
| material | steel: E = 200000 MPa, nu = 0.3, rho = 0.00785 g/mm3 |
| allowable stress | yield 250 MPa / safety factor 1.5 = 166.667 MPa |
| deflection limit | L / 100 |
| units | mm, N, MPa (the deck must use this consistent set) |

## Non-goals

- anything but a prismatic rectangular beam (no tapering, holes, brackets)
- dynamics, fatigue, buckling, non-linear materials or large deflections
- the agent does not choose loads, material or limits — they are fixed above
- mass is reported, not gated; "minimise mass" is the design intent

## Artifact

A directory containing two files:

1. `design.json` — the geometry the agent chose:
   `{"L": <mm>, "b": <mm>, "h": <mm>, "mesh_size": <mm>}`
   `mesh_size` is the target element edge length; the judge meshes `mesh_size`
   and `mesh_size/2`.
   Constraints: `L >= 5*max(b,h)` (must be a slender beam),
   `mesh_size <= min(b,h)/2`, and <= ~150k elements per mesh.

2. `beam.inp` — the CalculiX deck. The judge generates `mesh.inc`
   (written next to the deck before `ccx` runs) containing:
   - `*NODE`, `*ELEMENT,TYPE=C3D8,ELSET=EALL`
   - `*NSET` `NFIX` (all nodes on the x=0 face), `NTIP` (x=L face),
     `NLOAD` (exactly the 4 corner nodes at x=L),
     `NEVAL` (stress evaluation nodes), `*ELSET` `EMEAS`
   The deck must `*INCLUDE, INPUT=mesh.inc`, assign the steel material to
   `EALL`, clamp `NFIX` (dofs 1–3), apply `-P/4 = -250.` N in dof 3 on `NLOAD`,
   and request `U` (`*NODE FILE`) and `S` (`*EL FILE`) output.

## Judge gates (all must pass)

1. **verification** — the deck is run on a fixed reference beam
   (L=1000, b=50, h=100 mm, 5 mm mesh). Tip deflection and wall bending
   stress must match Euler-Bernoulli within **3%**. This exercises the
   agent's deck end to end (BCs, load, units, output requests).
2. **convergence** — the design is run on `mesh_size` and `mesh_size/2`
   meshes; tip deflection and stress must change by **<= 2%**.
3. **spec_limits** — on the finer design mesh:
   `sigma_wall <= 166.667 MPa`, `delta_tip <= L/100`, and both quantities
   must sit within a sanity band of the EB estimate (delta ratio in
   [0.85, 1.15], stress ratio in [0.75, 1.25]) so a wrong BC or load that
   "passes" the limits is still caught.
4. **mass** — reported: `rho * L * b * h` in grams (informational).

## Acceptance oracle

Independent Euler-Bernoulli beam theory, computed inside the judge:

- `delta_EB = P L^3 / (3 E I)`, `I = b h^3 / 12`
- `sigma_EB = P L / Z`, `Z = b h^2 / 6`

FEA tip deflection = max `|U3|` over `NTIP`. FEA wall stress = max von Mises
over `NEVAL` nodes (outer fibres, interior width, `0.3h <= x <= h` — the
clamped-face corner singularity and the loaded corner nodes are excluded by
construction) scaled by `L/(L-x)` to the wall bending moment.

Validation happens before any solve: missing/invalid fields, non-slender
geometry or an oversized mesh fail every gate.

## Self-test

`judge/mutants.py` writes scripted single-edit mutants of `examples/good`
(wrong units, propped tip, load on the wrong node set, too-coarse mesh,
10x overload, undersized section, missing output); each mutant and the
gate that kills it is listed in `examples/bad/README.md`.
`judge/selftest.sh` requires the good artifact to pass, >= 90% of the
mutants to fail, and two grades of the good artifact with the same
`--seed` to give byte-identical verdict JSON except the `timing` key.
