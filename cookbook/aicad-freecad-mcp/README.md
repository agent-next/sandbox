# AI-CAD part design: FreeCAD driven through an MCP server, judged from the delivered files

This demo shows the real AI-CAD user flow. A user gives their agent a short
text spec for a machined part; the agent works inside a disposable agent-next
sandbox, drives FreeCAD 1.0.1 through the
[freecad-mcp](https://github.com/neka-nat/freecad-mcp) MCP server, and
delivers STEP/STL (and a DXF drawing for the plate). A judge the agent cannot
fool then decides from the delivered files alone — re-importing the B-rep
with CadQuery/OCP, checking mesh topology with trimesh, comparing against a
reference solid with manifold3d boolean XOR, and auditing the DXF with
ezdxf. A sandbox helps because CAD toolchains are heavy (an ~850 MB pinned
FreeCAD, plus a Python judge stack) and the tool must not be able to touch
the judge.

Three parts of rising difficulty: a flanged bushing, an adapter plate with a
6-hole bolt circle, and an L-bracket with an R8 fillet (specs in
`specs/*.md`, gates and numeric rules in `SPEC.md`).

## One-command run

```bash
pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"
export SBX_API_KEY=<your key>
python3 cookbook/aicad-freecad-mcp/run.py            # add --ref <branch> to test a branch
```

`run.py` creates a sandbox, runs `judge/setup.sh` (pinned, sha256-checked
downloads), starts the FreeCAD GUI under Xvfb with the freecad-mcp addon
(RPC server on 127.0.0.1:9875), drives the freecad-mcp MCP server with a
scripted stdio client that executes the checked-in agent build scripts
inside FreeCAD, then runs `judge/selftest.sh` and `judge/grade.sh` on each
delivered part. No LLM key is needed anywhere: the "agent output" is checked
in, so the run is deterministic — the loop below is what a real agent does
instead.

Measured wall time on a 2-vCPU sandbox (see RECEIPT.md for the full runs):
setup ~7 min (dominated by the FreeCAD AppImage download/extract), MCP drive
of all three parts ~5 s, selftest ~1.5 min, each grade < 5 s. Limits: the
AppImage download is ~850 MB; `--timeout-min 30` covers a cold run.

## Ask your agent

Paste this to your own agent (it needs the sandbox plugin / `sbx` CLI and a
key in the environment):

> Create an agent-next sandbox and inside it: clone this repo, `cd
> `cookbook/aicad-freecad-mcp`, and run `bash judge/setup.sh`. Read
> `specs/bushing.md`, `specs/plate.md` and `specs/bracket.md`, and write your
> own FreeCAD build script for each part (see `agent/build_*.py` for the
> expected shape of a script, but write yours from the spec — do not copy
> them; keep to the exact dimensions, they are not design freedom). Deliver
> each part as `<part>.step` + binary `<part>.stl` in one directory, plus
> `plate.dxf` for the plate, by running your scripts through the freecad-mcp
> MCP server started inside the sandbox (like
> `driver/drive_freecad.py` does, with FreeCAD under Xvfb). Then grade
> yourself with `bash judge/grade.sh <your-artifact-dir> --json v.json`
> until every gate passes — the judge re-imports your STEP with
> CadQuery/OCP, checks your STL with trimesh, XORs it against its own
> reference solid with manifold3d, and audits your DXF with ezdxf; it must
> not be fooled. Iterate on your own design until `grade.sh` exits 0 for
> all three parts.

The demo's own checked-in artifacts (`examples/good/`) were produced exactly
this way, through the MCP server, and are what `run.py` grades.

## What the judge checks (see `SPEC.md` for numbers)

- B-rep: STEP re-imports as exactly 1 valid solid (OCCT BRepCheck_Analyzer),
  volume within 0.5 % of the closed-form analytic volume
- bbox within 0.05 mm per axis of the spec box
- STL: watertight, winding-consistent (trimesh), volume within 0.5 %
- XOR: manifold3d symmetric difference vs a judge-built CadQuery reference
  solid <= 1 % of reference volume
- features: cylindrical-face inventory — radii within 0.05 mm, hole count,
  bolt-circle angular spacing within 0.1°, fillet radius and axis position
- manufacturability: sampled minimum wall thickness >= 1.2 mm
- DXF (plate): ezdxf audit clean, 7 circles + a centred 100 × 80 outline

The self-test rebuilds 7 scripted single-edit mutants of the good artifacts
(wrong bore, missing flange, wrong hole count/drift, inch-scaled plate,
missing fillet, hole-punched STL, flipped facets) and requires every one to
be killed — 100 % on the current set.

## Tooling

| tool | pin | licence |
|---|---|---|
| FreeCAD | 1.0.1 conda AppImage (sha256 in `judge/setup.sh`), run not vendored | LGPL-2.1+ |
| freecad-mcp | git `78bf0230a03324b56c9a0b7f55150fb5be2a0d42` | MIT |
| trimesh / manifold3d / cadquery (OCP) / ezdxf / rtree / numpy | pinned in `judge/requirements.txt` | per package |

Tool downloads are checked with sha256; `judge/VERSIONS.txt` records what
setup actually installed. `examples/bad/` is generated scratch (git-ignored).
