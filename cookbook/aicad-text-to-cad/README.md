# Text-to-CAD in an agent-next sandbox: three parts, one judge

An agent turns three short text specs (a flanged bushing, an adapter
plate with a bolt circle, an L-bracket with a fillet) into machined
parts — writing a model for the [text-to-cad] tool
([earthtojake/text-to-cad], MIT, published as the `cadgen` PyPI package,
pinned at 0.7.2), whose runtime executes it into the delivered STEP +
STL files. A judge the agent cannot fool then decides whether those
**delivered files** are the part the spec asked for, using four
independent sources of truth: the OCP CAD kernel (STEP re-import,
`BRepCheck_Analyzer` validity, exact B-rep volume/bounds/cylindrical
faces), trimesh (STL watertightness + winding), manifold3d (boolean XOR
against a reference solid built from the spec alone), and the
hand-written `judge/spec.json`. The tool runs for real on checked-in
agent-written models — deterministic, no LLM key needed for the
execution step; your agent is what writes the model.

A sandbox helps because CAD kernels and mesh oracles are heavy, pinned
and disposable: every run gets the exact tool versions, and nothing a
model script does can touch the judge (it is checksummed before and
after, and every artifact is graded in a scratch copy).

## One-command run

```bash
pip install "git+https://github.com/agent-next/sandbox#subdirectory=cli"
export SBX_API_KEY=<your key>
python3 run.py            # add --ref <branch> to test a PR, --part adapter_plate
```

Creates a 30-min sandbox → `git clone --depth 1` this repo →
`judge/setup.sh` → `judge/selftest.sh` → `judge/grade.sh
examples/good/bushing` → prints the verdict JSON → kills the sandbox
and confirms removal via `sbx list`. `--keep` leaves it up for
exploration. Exit non-zero on any failure.

Measured wall time per step (2 vCPU sandbox, RECEIPT.md has the full
transcript): setup ≈ 4 min (first run; ~40 s cached), selftest ≈ 8 min
(3 good parts + 8 mutants + determinism re-runs), grade ≈ 30 s per
part. Limits stated plainly: the judge needs ≥ CPython 3.12 (pinned
numpy/scipy wheels ship no cp311 build) and ~2 GB disk for the venv;
every grade is CPU-only.

## Ask your agent

Paste this into your agent (it runs inside any agent-next sandbox with
this repo checked out, or locally — the judge only needs
`bash judge/setup.sh` first):

> Work in `cookbook/aicad-text-to-cad/`. Install the pinned judge with
> `bash judge/setup.sh`, then read `judge/spec.json`: it is the contract
> for three parts (bushing, adapter_plate, bracket). For each part, you
> are the CAD agent: read `examples/good/<part>/spec.txt`, write your own
> `model.py` for the text-to-cad tool (cadgen 0.7.2 — decorate a
> function that returns build123d geometry with `@step()` and `@stl()`,
> import build123d as `from cadgen import build123d as bd`, and call the
> function under `if __name__ == "__main__":`; `python3 model.py` must
> write model.step and model.stl beside it). Do NOT copy
> examples/good — build from the spec text. Then iterate with
> `bash judge/grade.sh <your part dir> --json /tmp/v.json` until every
> gate passes: B-rep valid, STL watertight, bbox within 0.05 mm, volume
> within 0.5 % of analytic, XOR within 1 % of the reference, feature
> counts/radii/positions exact, min wall honoured. Read the failing
> gate's `measured` field — it names the number and the rule. When the
> last part passes, show me the three verdict JSONs.

The judge grades what you delivered, not what you intended: it rebuilds
your model with the pinned tool and requires byte-identical output, so
hand-edited files that the tool would not produce fail `delivery_matches`.

## The judge's gates

`judge/grade.sh <part_dir> [--seed N] [--json out.json]` — exit 0 only
if all 10 gates pass (SPEC.md has the full table): tool_runs,
delivery_matches (byte-identical regeneration), step_valid,
stl_valid, bbox ≤ 0.05 mm, volume_analytic ≤ 0.5 %, xor_volume ≤ 1 %,
features (counts/radii/centres/spacing — the only home-grown rules),
min_wall, judge_intact. `judge/selftest.sh` proves the judge fails
where it must: 8 single-edit mutants (wrong hole count, wrong
diameter, missing/wrong-radius fillet, ×25.4 scale slip,
non-watertight export, flipped facet, tangential hole drift) are each
killed, ≥ 90 % required — measured: 8/8.

## Numbers

All figures in RECEIPT.md come from the commands shown there; media/
regenerates from the same outputs via `media/make_media.sh` (not built
in this branch's initial commit).

## Licence / provenance

Tool: [text-to-cad][earthtojake/text-to-cad] by earthtojake, MIT,
`cadgen==0.7.2` from PyPI (sha256-pinned in `judge/requirements.txt`).
Judge oracles: trimesh 4.12.2 (MIT, Michael Dawson-Haggerty),
manifold3d 3.5.2 (Apache-2.0, Emmett Lalish), OCP 7.9 (LGPL-2.1,
OCCT) via cadquery-ocp-novtk 7.9.3.1.1 (Apache-2.0 wrapper), build123d
0.11.1 (Apache-2.0), ezdxf 1.4.4 (MIT, Manfred Moitzi) — all recorded
in `judge/VERSIONS.txt`.

[text-to-cad]: https://github.com/earthtojake/text-to-cad
[earthtojake/text-to-cad]: https://github.com/earthtojake/text-to-cad
