# SPEC — `cookbook/nanousd-render/`

An agent works on a real 3D-scene engineering problem inside a disposable
agent-next sandbox: author a small USD scene (colored meshes, a camera, a
light) that **two independent USD implementations agree on** — nanousd
(NVIDIA's experimental C-ABI Core-Spec implementation) and Pixar's usd-core —
and whose headless CPU render (nanousd's OpenGL ES renderer on Mesa
llvmpipe) draws exactly where an independent numpy pinhole-projection oracle
says it must.

## Goal

Author one USDA scene file so that:

1. both readers — nanousd (pinned commit) and usd-core (pinned pip wheel) —
   parse it and agree **exactly** on the graded mesh set, per-mesh point
   counts, and world transforms/bounding boxes;
2. the renderer rasterizes it headlessly on llvmpipe to a PNG sized
   640×480;
3. an independent projection oracle (numpy pinhole math, no USD code)
   agrees with the rendered pixels: every mesh lands where the math says,
   painted the color the file declares.

## Non-goals

- PBR materials, textures, MaterialX, MDL, USDZ/USDC (the artifact is USDA
  text).
- Artistic quality: composition beyond the "verifiable scene" layout rules.
- Animation, time samples, variants, instancing, references/sublayers —
  the scene must be a single self-contained layer; composition arcs that
  could make the two readers disagree on *what is in the stage* are out of
  scope and rejected (G1).
- Performance: no polygon budget beyond the point-count rule below.

## Artifact

One USDA file (the file graded by `judge/grade.sh <artifact>`), containing:

- **Meshes**: exactly 5 `def "Mesh"` prims directly under `/World`
  (`/World/Cube`, `/World/Wedge`, `/World/Cylinder`, `/World/Octahedron`,
  `/World/Tetra` in the known-good example; the names are free), each with:
  - authored `point3f[] points` with ≥ 12 points,
  - `int[] faceVertexCounts` and `int[] faceVertexIndices` describing a
    closed triangle or quad shell,
  - one constant `color3f[] primvars:displayColor = [(r, g, b)]` with
    L2 norm ≥ 0.45 (bright enough to tell from the render background) and
    pairwise L2 distance ≥ 0.30 between any two meshes' colors,
  - a transform authored as xformOps (`xformOp:translate` and optionally
    `xformOp:rotateXYZ`/`xformOp:scale`), no raw `matrix4d xformOp:transform`
    (keeps the two readers on the same code path).
- **Screen separation**: the meshes must compose so that their projected
  bounding rectangles (per the judge's projection) overlap pairwise by
  ≤ 10 % of the smaller rectangle's area — the oracle needs each mesh's
  pixels uncontaminated. This is a layout constraint on the design, like a
  spec mask in an analog demo.
- **Camera**: exactly one `def "Camera"` prim under `/World`, positioned and
  rotated via xformOps (USD cameras look down local −Z, +Y up; e.g.
  translation `(0, y, d)` plus `rotateX(-90°−θ, ...)` style tilt), with
  **explicitly authored** `float focalLength`, `float horizontalAperture`,
  `float verticalAperture` (aperture ratio 4:3 ± 5 %, matching the judge's
  640×480 render) and `float2 clippingRange`.
- **Light**: at least one `DistantLight`, `DomeLight` or `RectLight` prim
  with authored `inputs:intensity` > 0. (The renderer's displayColor raster
  path uses default lighting; the light prim is a structural requirement of
  the scene, not what the raster path consumes.)
- No composition arcs (`references`, `payload`, `subLayers`, `inherits`,
  `variantSets`, `instanceable`), no `Skel`/`Physics`/plugin schemas: a
  self-contained, core-spec-only scene. Anything the two readers could
  disagree on is rejected before it is rendered.

## Judge gates (`judge/grade.sh <artifact> [--seed N] [--json out.json]`)

All gates numeric and deterministic; exit 0 only if all pass. `--seed` is
accepted for interface uniformity (nothing in this judge is random).

- **G1 structure (both readers)**: nanousd's C API *and* usd-core open the
  file with no errors; both see **exactly 5** `Mesh` prims under `/World`,
  **exactly one** qualifying `Camera`, and at least one qualifying light with
  authored `inputs:intensity > 0`; every mesh meets the
  point-count, color-brightness and pairwise-color-distance rules; the
  camera meets the authored-intrinsics, 4:3 aperture and authored
  `clippingRange` rules; no forbidden composition arc or property is
  authored, including the ban on a raw `matrix4d xformOp:transform`. All 5
  meshes meet every structural rule under both readers (fail closed on
  divergence).
  Composition arcs and plugin schemas are rejected **as the parsers report
  them** (the usd-core dumper lists Sdf arc fields and prim types), plus a
  second text net with comments stripped and all whitespace removed — a
  mutant smuggles an `inherits=[</Nope>]` arc past any spaced-token scan,
  which is exactly the formatting cheat that report closes.
- **G2 cross-reader agreement (the heart of the demo)**: the two readers
  must agree on the **exact set of prim paths under `/World`** (a prim one
  reader silently drops is a divergence whatever its type), and for every
  graded mesh, nanousd and usd-core must agree on
  - prim path: **exact** string equality of the mesh path sets;
  - point count: **exact** integer equality;
  - world 4×4 transform: max |Δ| ≤ **1e-9** per entry — the judge composes
    each mesh's world matrix itself from **both readers' own local
    transforms** (ancestor chain, `resetXformStack!` honoured), so a local
    transform a reader resolves wrongly cannot hide behind the comparison;
    usd-core additionally reports its own resolved world matrix, which the
    judge cross-checks against its own composition to the same 1e-9;
  - world bounding box (judge-computed from each reader's own resolved
    `points` and world transform): max |Δ| ≤ **1e-6** per coordinate.
  The camera's world transform and authored intrinsics must also agree
  ≤ 1e-9.
- **G3 headless render**: the nanousd OpenGL ES renderer, on llvmpipe
  (EGL pbuffer, no X, no GPU), renders the scene at **640×480** RGBA8 twice
  (to prove byte-determinism) with a judge-supplied camera derived from the
  artifact's camera — the eye, forward and up vectors and the vertical field
  of view all come from the file camera's own world basis and its authored
  `focalLength`/`verticalAperture`, so the camera is the artifact's, not the
  judge's — and writes one PNG. The image must decode, be
  640×480, and ≥ 1 % of pixels must differ from the corner background pixel
  by > 0.05 per channel.
- **G4 projection oracle (independent numpy math)**: from the camera's world
  transform and authored intrinsics the judge projects every graded mesh's
  world bbox corners through its own pinhole model (no USD code) to a
  pixel-space axis-aligned rectangle, and requires
  - per mesh: rectangle area ≥ **400 px²** and ≥ **90 %** of the
    **unclamped** rectangle is on-screen — the area and the on-screen
    fraction are measured on the rectangle as the math computes it, and the
    clamping to the frame is applied only when pixels are sampled in it, so
    a partially off-screen mesh fails instead of silently measuring as
    100 % (kills off-frame meshes and a camera pointed away);
  - pairwise: rectangle overlap ≤ **10 %** of the smaller area (the layout
    rule, re-measured by the judge's own math);
  - per mesh, a **color-proportionality fit** on the inner rectangle (the
    middle 50 % of each side). The pinned raster shader is exactly
    multiplicative in `displayColor` (`color = displayColor × illuminance`,
    gamma 2.2 at output), so the oracle gamma-decodes the inner-rect median
    and requires `median_linear ≈ k · displayColor`: one fitted illuminance
    `k` per mesh in **[0.06, 1.30]** with per-channel deviation ≤ **35 %**,
    and every other graded mesh's color must fit the same pixels worse by
    ≥ **max(30 %, 1.6×)** (kills recolored or swapped meshes — and a rect
    that samples background fits nothing, killing mis-projection too).

## Acceptance oracle (independent of "it ran")

1. **Reference tool**: usd-core is the reference reader; agreement with it
   (G2) is a cross-implementation check, not self-consistency.
2. **Analytic projection**: G4 is closed-form pinhole math in numpy —
   the judge's own view/proj matrices from the camera world transform and
   authored intrinsics — checked against the actual rendered pixels, so a
   scene that renders somewhere other than where the file says cannot pass.
   The color rule is likewise analytic: the pinned shader's response is
   multiplicative in `displayColor` (see `shaders_gles.h` in the pinned
   source), so the oracle fits `median_linear = k · displayColor` per mesh
   and demands the fit be decisive against every other mesh's color.
3. **Fail-closed parsing**: either reader refusing the file, or any
   divergence between them, fails the grade; there is no
   partially-verified pass.
4. **Determinism**: G3 renders twice and compares bytes; the whole verdict
   JSON (excluding the `timing` key) is byte-identical across runs (checked
   by the self-test).

## Self-test (`judge/selftest.sh`)

- The known-good example passes all gates.
- ≥ 5 known-bad single-edit mutants, generated by `judge/mutants.py`, each
  fail ≥ 1 gate — including: a mesh translated far out of frame and a second
  one placed about half out of frame (both killed by G4's on-screen rule), a
  mesh recolored to a near-duplicate of another, a camera rotated to look
  away, a malformed (syntax-broken) file, a prim typed with a plugin schema
  (`SkelRoot`: both readers keep the prim and still agree, so it is G1's
  forbidden-schema rule that fires, not a G2 prim-set divergence), two
  meshes whose projected rectangles overlap past the layout rule, and a
  composition arc smuggled in without the spaces a text-only scan
  matches (the forge-a-pass cheat; the parser-reported arc check kills it).
  Every mutant carries the gate it must fail and the self-test fails a
  mutant whose kill lands on a different gate.
- **A kill counts only when a judge gate fails**: grade.sh exits non-zero
  *and* the verdict JSON parses *and* at least one gate has `pass: false`.
  A non-zero exit with no gate verdict is a crash, not a kill, and fails
  the self-test; the kill rate is counted that way and must be ≥ 90 %
  (the mutants here reach 100 %). Every mutant must also fail the gate
  `mutants.py` names for it.
- Verdict-JSON determinism across two runs checked on every self-test.

## Judge-integrity rule

The artifact is graded from a temp copy, and it is **only ever parsed and
rendered out of process**: the nanousd C dumper, a usd-core dumper
(`judge/usdcore_dump.py`) and the C renderer driver are separate
processes, so a crafted USDA cannot touch the judge's own process, and
every judged quantity is re-derived by the judge from those helpers'
output files. Reader and renderer subprocesses carry timeouts (a hung
helper is a gate error, never a hang). The judge hashes its own `judge/`
tree before and after every grade and fails closed on any change.

## Tools (pinned by `judge/setup.sh`; versions recorded in `judge/VERSIONS.txt`)

- nanousd + nanousd-opengl-renderer from
  `github.com/NVIDIA-Omniverse/omniverse-labs`, `projects/nanousd-labs`,
  at git commit **ea045a027c4d0cc717174ed92f13ba56fffeb39d** (Apache-2.0),
  built with a pinned CMake release tarball (sha256-checked) + Debian
  bookworm `ninja-build` + Debian Mesa (llvmpipe/EGL) + whatever MaterialX
  version that commit's FetchContent pins. nanousd's `compliance_test` must
  pass post-build.
- usd-core **25.5.0** (pip wheel, exact), numpy **2.2.6**, Pillow **11.2.1**
  (pinned by `judge/requirements.txt`).
- Judge engine: Python ≥ 3.10 (stdlib + the pinned wheels), one small C
  dumper (`judge/nanousd_dump.c`) and one small C renderer driver
  (`judge/render_once.c`) compiled against the pinned sources.
