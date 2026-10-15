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
  file with no errors; both see ≥ 4 `Mesh` prims under `/World`, ≥ 1
  qualifying `Camera`, ≥ 1 qualifying light; every mesh meets the
  point-count, color-brightness and pairwise-color-distance rules; the
  camera meets the authored-intrinsics and 4:3 aperture rules; no forbidden
  composition arc or property is authored. All 5 meshes meet every
  structural rule under both readers (fail closed on divergence).
- **G2 cross-reader agreement (the heart of the demo)**: for every graded
  mesh, nanousd and usd-core must agree on
  - prim path: **exact** string equality of the mesh path sets;
  - point count: **exact** integer equality;
  - world 4×4 transform: max |Δ| ≤ **1e-9** per entry (both computed by the
    judge from each reader's resolved local transforms);
  - world bounding box (judge-computed from each reader's own resolved
    `points` and world transform): max |Δ| ≤ **1e-6** per coordinate.
  The camera's world transform and authored intrinsics must also agree
  ≤ 1e-9.
- **G3 headless render**: the nanousd OpenGL ES renderer, on llvmpipe
  (EGL pbuffer, no X, no GPU), renders the scene at **640×480** RGBA8 twice
  (to prove byte-determinism) with a judge-supplied camera derived from the
  artifact's camera (eye/fov from the file; a fixed cannonical aim-at-scene
  up-vector convention), and writes one PNG. The image must decode, be
  640×480, and ≥ 1 % of pixels must differ from the corner background pixel
  by > 0.05 per channel.
- **G4 projection oracle (independent numpy math)**: from the camera's world
  transform and authored intrinsics the judge projects every graded mesh's
  world bbox corners through its own pinhole model (no USD code) to a
  pixel-space axis-aligned rectangle, and requires
  - per mesh: rectangle area ≥ **400 px²** and ≥ 90 % of the rectangle is
    on-screen (kills off-frame meshes and a camera pointed away);
  - pairwise: rectangle overlap ≤ **10 %** of the smaller area (the layout
    rule, re-measured by the judge's own math);
  - per mesh: the **median** color of the rendered pixels in the inner
    rectangle (the middle 50 % of each side) matches the authored
    `displayColor` within **0.22** per channel, and the inner-rectangle
    mean color is closer (by ≥ **1.6×**) to its own displayColor than to any
    other graded mesh's color (kills recolored or swapped meshes).

## Acceptance oracle (independent of "it ran")

1. **Reference tool**: usd-core is the reference reader; agreement with it
   (G2) is a cross-implementation check, not self-consistency.
2. **Analytic projection**: G4 is closed-form pinhole math in numpy —
   `x_px = W·(1/2 + (X/−Z)·f/hAp)/2`·... — see `judge/judge.py:project_rect`
   for the exact formula — checked against the actual rendered pixels, so a
   scene that renders somewhere other than where the file says cannot pass.
3. **Fail-closed parsing**: either reader refusing the file, or any
   divergence between them, fails the grade; there is no
   partially-verified pass.
4. **Determinism**: G3 renders twice and compares bytes; the whole verdict
   JSON (excluding the `timing` key) is byte-identical across runs (checked
   by the self-test).

## Self-test (`judge/selftest.sh`)

- The known-good example passes all gates.
- ≥ 5 known-bad single-edit mutants, generated by `judge/mutants.py`, each
  fail ≥ 1 gate — including: a mesh translated out of frame, a mesh
  recolored to a near-duplicate of another, a camera rotated to look away,
  a malformed (syntax-broken) file, and a prim typed with a schema one
  reader knows and the other silently drops (`SkelRoot`: usd-core reads it
  as a prim under `/World`, nanousd does not, so G1/G2 diverge).
- Kill rate ≥ 90 % printed; exit non-zero otherwise; verdict-JSON
  determinism across two runs checked on every self-test.

## Judge-integrity rule

The artifact is graded from a temp copy; the judge hashes its own `judge/`
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
