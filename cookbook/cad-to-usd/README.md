# cad-to-usd — CAD to OpenUSD conversion, checked by an independent CAD kernel

An agent converts real CAD parts to OpenUSD `.usda` inside a disposable
agent-next sandbox: it fetches three pinned parts from NVIDIA's public
RC-Car-CAD repo, writes a `convert.sh` driving the `usd-convert-cad`
converter, and iterates until the judge passes. The judge never trusts
"the converter ran": OpenCASCADE (`cadquery-ocp`) reads the same STEP/IGES
sources and computes the exact bounding box and surface area, and
`usd-core` reads the produced USD and measures the mesh — bounding boxes
must agree within 1 % per axis and total triangle area within 3 %.

Fixed spec (`SPEC.md`): three parts from the RC-Car-CAD repo at commit
`407bd55` (the Futaba servo as STEP and as IGES, plus the front shock
tower), `metersPerUnit = 0.001` (millimeter scene), `upAxis = "Z"`, ASCII
`.usda` per part, converter `usd-convert-cad 0.3.0`.

## Ask your agent

> Clone https://github.com/agent-next/sandbox into this sandbox and run
> `bash cookbook/cad-to-usd/judge/setup.sh` (installs the pinned
> `usd-convert-cad` converter and the judge oracle under `~/.venvs`).
> Convert the three pinned RC-Car-CAD parts from the spec in
> `cookbook/cad-to-usd/SPEC.md`: produce an `artifact/` with one
> `<key>.usda` per part (millimeter scene, Z up) and a `convert.sh` that
> regenerates them from `sources/` using `$USD_CONVERT_CAD`. Then run
> `cookbook/cad-to-usd/judge/grade.sh artifact` and iterate until every
> gate prints PASS.

## One-command run

```bash
python3 run.py            # clones this repo at main into a fresh sandbox
python3 run.py --ref my-branch --keep
```

Needs the `sbx` CLI (`pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"`)
and `SBX_API_KEY` in the environment. It creates a sandbox, clones the repo,
runs `judge/setup.sh`, `judge/selftest.sh`, and `judge/grade.sh
examples/good --seed 42`, prints the verdict JSON, and kills the sandbox
(verifying it is gone with `sbx list`).

Without the `sbx` CLI or a key, run the same steps inside any Debian 12 box
with python3.12 and internet:

```bash
bash judge/setup.sh
bash judge/selftest.sh
bash judge/grade.sh examples/good --seed 42 --json /tmp/verdict.json
```

Measured on a 2 vCPU / 4 GB sandbox (real output in RECEIPT.md):

| step | wall time |
|---|---|
| setup (two pinned venvs, ~630 MB of sha256-checked wheels) | 4 min |
| selftest (good ×3 grades + 9 mutants, kill rate 100 %) | 20 min |
| grade the good artifact (fetch + oracle + re-conversion) | 5 min |

## How the judge works

- `judge/setup.sh` — creates two venvs under `~/.venvs`: the converter
  (`usd-convert-cad==0.3.0`, 485 MB wheel) and the judge oracle
  (`usd-core==26.8` + `cadquery-ocp==7.9.3.1.1`). Every wheel is installed
  with `pip --require-hashes` from the pinned `judge/requirements-*.txt`.
  The venvs are separate on purpose: the converter's bundled USD and the
  judge's usd-core conflict in-process.
- `judge/grade.sh <artifact> [--seed N] [--json out.json]` — fetches the
  three pinned RC-Car-CAD sources (sha256-verified against
  `judge/sources.txt`, fetched at run time, never committed) and runs six
  gates; exit 0 only if all pass:
  1. **file_set** — all three `<key>.usda` present, non-empty, distinct;
  2. **stage_meta** — `metersPerUnit = 0.001` (±1e-9), `upAxis = "Z"`,
     valid default prim;
  3. **geometry_counts** — `prims > 0`, `meshes > 0` per part;
  4. **bbox_match** — USD world bbox vs the OpenCASCADE oracle bbox
     (`BRepBndLib.AddOptimal`), per-axis endpoint deltas within 1 % of the
     oracle extent (0.1 mm absolute floor);
  5. **area_match** — total triangle area within 3 % of the OpenCASCADE
     exact face area (`BRepGProp.SurfaceProperties`);
  6. **conversion_script** — `convert.sh` re-run on fresh sources
     reproduces all three parts, and the regenerated parts themselves
     pass gates 2–5; the judge's converter-invocation log must show every
     pinned source was actually converted (an artifact that ships
     pre-made outputs and copies them into place fails here).
- `judge/selftest.sh` — the good artifact must pass; every known-bad
  mutant from `judge/mutants.py` must be killed by a judge gate (10
  mutants: wrong units, up-axis metadata flip, Y/Z geometry swap, dropped
  mesh, decimated mesh, empty stage, garbage STEP through `convert.sh`,
  the ship-outputs-and-copy-them cheat, missing part, cross-part copy;
  a grade that crashes the judge without a verdict does not count);
  kill rate must be ≥ 90 %; two grades with the same seed must be
  byte-identical except the `timing` key.
- The artifact runs out of process in a scratch copy; `judge/`, the two
  pinned venvs and the fetched sources are all checksummed before and
  after grading, so the artifact cannot modify the judge or forge its
  oracle.

## Limits

- Fixed problem statement: the parts, units and up-axis are pinned in
  SPEC.md — the judge tests exactly this conversion, done correctly.
- Comparison is geometric (bbox + total area), not a per-face correspondence;
  a tessellation that hit the tolerances while locally distorting geometry
  is out of scope for this judge.
- STEP and IGES inputs only, via `usd-convert-cad`; no material or lighting
  fidelity is graded.
- The converter wheel is ~485 MB: budget ~5 min and ~3 GB disk for setup
  on a fresh sandbox.
