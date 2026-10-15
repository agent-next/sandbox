# AI-CAD with CADAM's kernel — text-to-CAD judged to 0.05 mm

This demo shows a real AI-CAD user flow inside a disposable agent-next
sandbox: an agent turns a short text spec into mechanical parts — OpenSCAD
source, STL mesh, STEP B-rep and (where asked) a DXF drawing — using the
same CAD kernel generation as [CADAM](https://github.com/Adam-CAD/CADAM)
(GPL-3.0, commit `eb216809c04fc353a58c3806e01e8b6676ee8488`), the
open-source text-to-CAD web app. Its pipeline is *text → LLM-written
OpenSCAD → OpenSCAD engine → STL/DXF*. The LLM step needs a key the
sandbox does not have, so the demo runs the deterministic half headless:
the pinned native OpenSCAD 2021.01 CLI (the engine generation CADAM
vendors as openscad-wasm) compiles the agent-written `.scad`. A judge
the agent cannot fool then decides from the delivered files alone —
B-rep validity, mesh watertightness, volumes against closed-form
analytic values, a boolean-XOR against a reference solid rebuilt by the
judge with OCCT, feature diameters/positions, and a minimum-wall
manufacturability rule. A sandbox helps because the whole CAD/OCCT
toolchain is heavy, GPL-licensed and disposable here — nothing touches
your machine.

## Ask your agent

Paste this to your agent (plugin users; it designs the parts itself and
iterates against the judge):

> In an agent-next sandbox, clone
> `https://github.com/agent-next/sandbox` at ref `main` and read
> `cookbook/aicad-cadam/SPEC.md`. Do the whole job inside the sandbox.
> For each of the three part specs in SPEC.md (bushing, plate, bracket):
> author the part as parametric OpenSCAD source (`part.scad`), export
> `part.stl` with OpenSCAD 2021.01, author an analytic-face STEP B-rep
> (`part.step`), and for the plate also `drawing.scad` + `drawing.dxf`
> (top view). Iterate with `bash judge/grade.sh <your artifact dir>
> --json /tmp/v.json` until every gate passes, then run
> `bash judge/selftest.sh` and report the kill rate and the per-case
> verdict JSON. The CADAM flow you are mirroring is: text spec →
> OpenSCAD source → OpenSCAD engine → STL/STEP/DXF deliverables
> (CADAM's own LLM step is out of scope without its API key; you are
> the LLM step).

## One-command run

```
export SBX_API_KEY=<your key>
pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"
python3 cookbook/aicad-cadam/run.py
```

`run.py` creates the sandbox, clones the repo, runs `judge/setup.sh`,
`judge/selftest.sh` and `judge/grade.sh` on the three known-good parts,
prints each verdict JSON, and always kills the sandbox (confirming with
`sbx list`), unless `--keep`.

## What the judge checks (all numeric, all from pinned libraries)

For each part: OpenSCAD re-export from the shipped source; STL matches
the re-export (manifold3d XOR); watertight + consistent winding (trimesh);
bbox within 0.05 mm; STL volume within 0.5 % of the analytic value;
XOR against the judge-built OCCT reference solid within 1 % of reference
volume; STEP re-imports valid (BRepCheck_Analyzer) with volume within
0.5 % of analytic; cylindrical-face count/radii; planar minimum wall
≥ 2.0 mm; spec rules (bolt-circle radius/spacing, ligaments, fillet
radii); for the plate, the DXF audits clean (ezdxf) and its loops carry
the right hole count/radii/positions. Tool versions and hashes:
`judge/requirements.txt`, `judge/package-sha256.txt`, `judge/VERSIONS.txt`.

## Measured wall time (2 vCPU sandbox, 2026-10-14, see RECEIPT.md)

| step | time |
|---|---|
| `judge/setup.sh` (fresh venv) | ~1 min |
| `judge/selftest.sh` (3 good + 11 mutants + determinism) | ~2.5 min |
| `judge/grade.sh` bushing / plate / bracket | 4 s / 16 s / 3 s |

Limits: parts sized to grade in seconds; a full run fits the 30-minute
sandbox timeout with >20 min headroom. If you have an LLM key for a
text-to-CAD service you can run CADAM's web UI (`npm i && npm run dev`
in its repo) on a sandbox port and screenshot it for your write-up; the
graded flow is the headless one above.

## Licence notes

OpenSCAD is GPL-3.0 — run here from a Debian package, never vendored.
CADAM is cited by URL + commit, not installed or copied. The judge stack
(trimesh MIT, manifold3d Apache-2.0, ezdxf MIT, cadquery-ocp Apache-2.0)
is installed as pinned wheels. No CADAM or OpenSCAD code is in this repo.
