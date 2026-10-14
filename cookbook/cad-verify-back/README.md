# cad-verify-back: mechanical CAD with CadQuery, judged from the delivered files

An agent designs an industrial adapter plate (plate + central bore + raised
boss + bolt circle) with **CadQuery 2.7.0** on OCCT from a customer spec JSON,
and delivers `part.step`, `part.stl` and `part.dxf`. A judge it cannot fool
then **verifies what was delivered, never the in-memory model**: it
re-imports the STEP through OCCT (solid count, bbox, volume vs a closed-form
analytic volume, through-hole count/diameters, bolt-circle PCD and angular
spacing), parses the STL with its **own** stdlib binary/ASCII parser
(watertightness, winding consistency, divergence-theorem volume), reads the
DXF with ezdxf (circle count/diameters/positions, outline), and checks the
design rules (minimum edge distance, minimum ligament) from the delivered
geometry. Nothing the agent exports can touch the judge's oracle.

Why a sandbox helps: the CAD toolchain (CadQuery/OCCT + GL runtime libraries)
is heavy and pinned; the agent installs it, iterates on its own geometry and
re-grades as often as it likes in a disposable environment, and the repo stays
clean of any of it.

## The one-command run

```bash
python3 run.py                # ref defaults to main; --ref <sha|branch> to override
```

Creates a sandbox, clones this repo, runs `judge/setup.sh`,
`judge/selftest.sh` and `judge/grade.sh examples/good`, prints the verdict
JSON + kill rate, then kills the sandbox (unless `--keep`). Needs the `sbx`
CLI and `SBX_API_KEY` (or `E2B_API_KEY`).

Measured wall time per step (2 vCPU sandbox, see RECEIPT.md for full output):

| step | wall time |
|---|---|
| `sbx create` | ~5 s |
| clone (depth 1) | ~5 s |
| `judge/setup.sh` (apt + 44 pinned wheels, ~300 MB) | ~2–4 min |
| `judge/selftest.sh` (good + 8 mutants + determinism) | ~5 min |
| `judge/grade.sh examples/good` | ~25 s |

Limits, stated plainly: the judge needs ~1.5 GB of RAM for the OCCT
re-import; grading a mutant that produces a huge STL would still finish but
the demo sizes parts in mm with meshes under ~1 MB. Setup dominates: the
pinned wheel set is ~300 MB to download once per sandbox. Nothing here is
parallelised; every gate is single-threaded and deterministic.

## Ask your agent (paste into a sandbox with this repo cloned)

> In `cookbook/cad-verify-back/`, read `SPEC.md` and the customer spec
> `judge/spec.json`. Using CadQuery 2.7.0 (already installed by
> `judge/setup.sh`; run it if `python3 -c "import cadquery"` fails), write
> `part.py` that builds the adapter plate exactly to that spec and exports
> `part.step`, `part.stl` (binary) and `part.dxf` (2-D top view: outline +
> CIRCLE per hole + boss OD) into your working directory. Then run
> `bash judge/grade.sh <your-directory>` and iterate on your own part.py
> until the verdict is `pass` with exit code 0. The judge only reads your
> three delivered files — it never runs your Python — and reports every
> measured vs expected number in its JSON. Do not modify anything under
> `judge/`; the judge checksums itself before and after grading.

A known-good `part.py` is in `examples/good/` (regenerate its exports with
`python3 examples/good/part.py`; they are gitignored).

## What the judge checks (full numeric rules in SPEC.md)

- **STEP** (re-imported through OCCT): 1 solid; bbox ≤ 0.01 mm from spec;
  volume ≤ 0.1 % from the closed-form `l·w·t + boss annulus − bore − bolts`;
  `bolt_n + 1` cylindrical through-holes with diameters ≤ 0.01 mm; bolt
  centres on the PCD within 0.02 mm, evenly spaced within 0.05°.
- **STL** (the judge's own parser, no mesh library): every edge shared by
  exactly 2 triangles; consistent winding; divergence-theorem volume within
  1 % of the STEP volume.
- **DXF** (ezdxf): `bolt_n + 2` CIRCLEs with diameters/positions to spec;
  closed rectangular outline `plate_l × plate_w` centred on the origin.
- **Design rules**: min edge distance and min ligament ≥ spec (0.01 mm slack).

The self-test (`judge/selftest.sh`) regenerates 8 single-edit mutants
(wrong bolt count, wrong PCD, bore +0.5 mm, boss missing, inch/mm ×25.4,
STL with one dropped facet, DXF missing a hole, edge-distance violation)
and requires every one to fail at least one gate — kill rate 8/8 = 100 %.

## Third-party sources

- CadQuery 2.7.0, Apache-2.0, https://github.com/CadQuery/cadquery
- OCCT via `cadquery-ocp` 7.8.1.1.post1, Apache-2.0, https://github.com/CadQuery/OCP
- ezdxf 1.4.4, MIT, https://github.com/mozman/ezdxf
- the good `part.py` was written for this demo; no third-party geometry files
  are used

Media (result figure, agent-loop figure, demo video): not done yet — a later
task builds `media/` for this demo (see the media section of
`cookbook/DEMO-STANDARD.md`).
