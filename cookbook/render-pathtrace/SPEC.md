# Material studio, CPU path tracing

## Goal and artifact

An agent designs `scene.json`: three to five procedural spheres with distinct
OpenPBR materials on a plane, lit by rect/sphere lights and a constant or
procedural environment. A fixed, trusted browser harness renders linear HDR
with [MuTracer](https://github.com/pissang/mutracer) 0.1.1 (MIT).
No executable artifact code, imported models, textures, network render assets,
denoising, media production, or GPU performance claims are in scope.

The driver supports `--backend cpu|gpu`. Both use WebGPU; CPU explicitly selects
SwiftShader. GPU leases are future work, not an acceptance prerequisite.

## Acceptance oracle

All five gates must pass. Input is strict JSON, all numeric values finite.
Unsupported fields fail rather than silently changing the scene.
The judge copies the artifact into a private temporary directory and compares
SHA-256 checksums of its own files before/after. Only the trusted harness runs
JavaScript. Seed defaults to 17 and can be overridden with `--seed`.

1. **G1, analytic furnace (independent of artifact).** Render diffuse spheres
   with albedos 0.18, 0.5, 0.8 in a constant environment of radiance L=1.
   Specular, coat, fuzz and emission are zero. Sphere interiors and background
   are selected by independent camera/ray geometry, excluding silhouettes.
   For each RGB-channel mean, require
   `abs(mean-rho*L) <= 4*sqrt(sum(pixel_sample_variances)/N**2) + 0.015*L`.
   Estimate variance of the pixel mean using independent seeded render blocks.
   The 1.5% bias allowance covers finite mesh normals and transport truncation,
   not a fitted correction. Background max error must be <= 1e-4.
   A self-test-only wrong-albedo switch must fail this gate.
2. **G2, energy.** Render every artifact material on an isolated furnace sphere.
   Non-emissive materials must have mean RGB <= 1.05*L in every channel.
   Emission is allowed only with an explicit `emissive: true` declaration;
   undeclared nonzero emission fails, including on the floor. Colors > 1 are
   rejected even if the renderer clamps them.
3. **G3, convergence.** Render the same artifact at >= four sample counts and
   compare linear-HDR RGB RMSE against an independent higher-spp reference.
   Fit `log(RMSE)` against `log(spp)`. Require slope in [-0.65, -0.35].
   Report all RMSEs, reference spp and slope. No denoising or adaptive sampling.
4. **G4, determinism.** Two renders at identical seed/settings must have
   byte-identical SHA-256 HDR hashes; seed+1 must change the hash.
5. **G5, studio spec.** Zero non-finite HDR values; tone map by
   `clip(linear_RGB, 0, 1)` (unit exposure, intentionally no highlight shoulder).
   Median Rec.709 luminance in [0.08, 0.85]; fraction of pixels with any
   tone-mapped channel >=1 at most 0.10. Relative RMS noise in the fixed
   foreground floor patch, measured between independent seeded buffers and
   divided by sqrt(2) and mean floor luminance, <=0.15.
   Resolution 64–128 pixels per side; final spp 16–64; entire grade <600 s.
   Three to five spheres and at least three distinct sphere materials,
   one floor; camera outside all spheres. Budgets fail before rendering.

The G5 limits above are initial engineering targets. Before claiming acceptance,
record measured good-scene values and freeze any justified adjustments here.
The low resolution is deliberate: this runs headless on two CPU cores with
about 3 GB RAM and software WebGPU.

## Judge self-test and reproducibility

Single-edit mutants: baseColor=1.6, undeclared floor emission, light intensity
x100, spp=1, camera inside a sphere, NaN material parameter, over-budget
resolution. Require all mutants rejected and kill rate >=90%.
Repeat grading with the same seed and compare complete verdicts after removing
only `timing`. Two fresh CPU sandbox receipts are required. Cross-sandbox G1,
G2 and G5 means must agree within 1e-4 and G3 slope within 1e-4 for the same
browser/adapter versions; timing may vary.

Independent reproduction by another model family is a pre-merge requirement;
unavailable reproduction must be marked not done, never inferred.
Media is explicitly deferred by the task owner.

## Dependency exception

MuTracer 0.1.1 was published 2026-10-14, inside the standard's two-week exclusion
window. The owner explicitly pins this release. Verify its supplied npm SHA-512
integrity before unpacking, additionally pin SHA-256, preserve package licences,
and run only in a disposable sandbox. Record the exception in `RECEIPT.md`.
