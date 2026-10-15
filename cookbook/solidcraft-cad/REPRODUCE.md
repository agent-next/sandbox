# REPRODUCE — independent reproduction of `cookbook/solidcraft-cad/`

**Reproducer:** GPT-6.1 Sol in Factory Droid (`droid exec`, reasoning high). That
is a different model family from the builder, which was Claude. It had only the
README and the repo. It was told not to open `examples/good/`,
`judge/mutants.py` or the judge code.

**Ref:** branch `sbx/demo-solidcraft-cad` at `a53bfad`, with one fresh sandbox
(`sbx create --timeout-min 60`). The run spanned 2026-10-14 to 2026-10-15.

## Part A: the README's numbers, from setup on a fresh sandbox

| step | exit | wall (remote) |
|---|---|---|
| `bash judge/setup.sh` (cold) | 0 | 255.9 s |
| `bash judge/selftest.sh` | 0 | 654.0 s (12 mutants at that ref) |
| `bash judge/grade.sh examples/good/design.json --json /tmp/v.json` | 0 | 39.8 s |

| number | README | reproduced | |
|---|---|---|---|
| self-test kill rate | 12/12 | 12/12 = 100 % | MATCH |
| OCCT volume / analytic volume | 16644.9 / 16644.9 mm³ | 16644.9 / 16644.9 mm³ | MATCH |
| volume relative deviation | 6.9e-10 | 6.94266e-10 | MATCH |
| mass | 44.94 g | 44.9412 g | MATCH |
| bolt holes, Ø / PCD / spacing deviation | 4, < 1e-13 | 4; 4.9e-15 mm, 7.1e-15 mm, 2.8e-14° | MATCH |
| min edge distance | 7.8 mm | 7.8 mm | MATCH |
| kernels agree: volume / area / centre of mass | 1.2e-6 / 4.9e-7 / < 1e-5 mm | 1.2234e-06 / 4.89179e-07 / 9.82488e-06 mm | MATCH |
| parametric ΔV (+2 mm), analytic ΔV | 5124.18 / 5124.18 mm³ | 5124.18 / 5124.18 mm³ (rel 5.1e-12) | MATCH |
| STL triangles / volume vs STEP | 3772 / 0.013 % | 3772 / 0.013085 % | MATCH (README now says 0.0131 %) |
| verdict | pass | `passed: true`, exit 0 | MATCH |

Tool versions from its setup run: solidcraft-cli 0.10.1 (tarball sha256
`2dee8297…700b`), Python 3.12.15, cadquery-ocp 8.0.1.0.0, vtk 9.6.2, numpy
2.5.3, matplotlib 3.11.2.

## Part B: the agent did the task itself

The reproducer wrote its own `design.json` from SPEC.md, spec.json and
`solidcraft-cli commands`, then graded it, up to 12 attempts:

| attempt | failed gate (judge at `a53bfad`) | how it modelled the part |
|---|---|---|
| 01 | features: bore 0 found, corner rounds 0/4 | rounded-rectangle sketch, cylinder boss, cylinder cuts |
| 02 | features | box + four vertical-edge fillets, `solid.hole` bore |
| 03 | features | two crossing boxes + four R5 cylinders, sketch-cut bore |
| 04 | features | lines + centre-point arcs outline |
| 05 | features | boxes + rotated corner/bore cylinders + `solid.combine` |
| 06–10 | features | further variants (overlapping sketches, scaled builds, translated build) |
| 11 | build | `solid.scale` factor `thickness / 1 mm` (a unit error, the agent's own mistake) |
| 12 | **pass** | rounded-rectangle sketch with all holes, net profile picked by point, annular boss at offset `thickness` |

Attempts 1–10 passed every other gate, including volume to 0.2 %, both
kernels agreeing, and the parametric rebuild. The agent inspected its own
STEP exports and found that SolidCraft writes some cylinders (after fillets,
rotations or booleans) as B-spline surfaces, which the features gate only
read as exact cylinders. It reported this as friction and did not touch the
judge.

## Lead follow-up: the reproduction found a judge bug, now fixed

These are valid designs, and the judge must accept every valid form of its
input (LESSONS.md). Fixes, each with its test first:

- `b5d7771` test: the self-test also grades `examples/good/design-csg.json`
  (the reproducer's attempt 05, unchanged). This fails on the old judge.
- `fe4f92d` fix: the features gate recognises a non-plane face as a Z-axis
  cylinder when 25 sampled normals are horizontal and the points fit one
  circle to 1e-4 mm (Kåsa least squares, stdlib).
- `d2b08ca` test: two mutants of the CSG design. One moves the bore 0.3 mm,
  which leaves the volume unchanged, so only the B-spline path can catch it.
  The other drops a corner round. Both are killed.

Every one of the reproducer's 12 attempts was re-graded with the fixed judge
(`d2b08ca`) in a fresh sandbox (lead, real output):

```
01 rc=0  02 rc=0  03 rc=0  04 rc=0  05 rc=0  06 rc=0  07 rc=0  08 rc=0  09 rc=0  10 rc=0
11 rc=1 build solidcraft-cli run exit 1: error: step 9 (solid.scale): invalid parameters for `solid.scale`: factors: expression: expec…
12 rc=0
```

The agent's first design was already correct. Only attempt 11, the agent's
own unit error, still fails, and it fails at build, as it should.

## Friction the reproducer reported, and what changed

| friction | change |
|---|---|
| README used bare `solidcraft-cli`, but setup does not put it on PATH | README "Ask your agent" now exports PATH first |
| features gate missed valid B-spline cylinders | fixed, see above |
| a long `sbx exec` (self-test, ~10 min) lost its stream (`ConnectError`), and one call hit `503 gateway is restarting` | `run.py` now starts each long step detached in the sandbox and polls for its exit code with short calls, retrying transport errors |
| setup took 256 s and self-test 654 s, slower than the README's 150 s / 480 s | README wall times updated from the two receipt runs |
| RECEIPT.md and media were not on the branch yet | added before merge |
| `sbx list` timed out three times at cleanup | platform issue, reported outside this repo; the sandbox itself was confirmed gone (`sbx kill`: not found) |

## Deviations

- The reproduction ran at `a53bfad`. The later commits change the judge's
  features gate (to accept more valid designs), the self-test (two known-good
  designs, 14 mutants), run.py's transport handling and docs. The good
  design's verdict numbers are unchanged by them: same values in both RECEIPT
  runs.
- The reproducer could not save a snapshot of its final design, because its
  60-minute sandbox expired first. It did not substitute any image.
