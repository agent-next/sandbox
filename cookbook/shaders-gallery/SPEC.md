# SPEC: Shaders Gallery (WebGPU shader hero sections in headless Chromium)

## Goal

Demonstrate an agent-next sandbox composing a hero section from the
popular open-source **shaders** component library
(<https://github.com/shader-effects-inc/shaders> — the npm package
`shaders`, ~4.8k GitHub stars), rendered headless in the sandbox using
Chromium's WebGPU-on-SwiftShader, and graded by an independent judge
that checks the rendered pixels, not the agent's claims.

- Upstream package: `shaders` on npm, **pinned to version 4.0.4**
  (2026-10-09), sha256-verified at setup time. MIT licence by
  Shader Effects Inc.; mini-COPY of the licence ships in the good example.
- Rendering backend: **WebGPU via Dawn/SwiftShader (CPU)** in headless
  Chromium 150.0.7871.100 (Debian bookworm, pinned + sha256-verified).
  WebGPU (not the WebGL fallback) is the only backend this demo grades;
  that choice is measured and recorded (see "Backend measurement" below).

## Non-goals

- The React/Vue/Svelte/Solid bindings, the partner bundle,
  `npx shaders` tooling, MCP servers. Only the framework-free
  `shaders/js` entry of the library is used.
- Building the library from source. The sha256-verified npm tarball is
  the only source of the library code.
- Native-gpu WebGPU, WebGL fallback grading, multiple effects composed in
  layers on one canvas, or the React wrapper's animation helpers. The
  judge drives `createShader` from `shaders/js` directly, one component
  per canvas.
- Video encoding. That is the media task's job; the judge produces PNG
  frames only.

## Artifact

One **artifact directory** — a static web page plus a manifest:

```
<artifact>/
├── index.html      # the hero section, served verbatim
├── artist.json     # the manifest (below)
└── LICENSE.shaders # copy of the MIT licence of shaders 4.0.4
```

`artist.json` describes what the agent *claims* it built:

```json
{
  "title": "Aurora Hero",
  "effects": [
    { "type": "Aurora",    "region": "hero-aurora" },
    { "type": "Blob",      "region": "hero-blob" },
    { "type": "ConicGradient", "region": "hero-conic" }
  ]
}
```

`type` must be an effect name from the pinned library's registry;
`region` must be the `id` of an element in `index.html` that contains
exactly one `<canvas>`. The judge serves the artifact verbatim over
HTTP, mounts each declared effect from the **sha256-verified local
library bundle** (never from the page's own copy) onto each region's
canvas, and grades the rendered pixels.

Anything else in the page (headings, copy, buttons, CSS) is fair game.
The artifact is graded in a scratch copy and may not write into
`judge/`; `judge/` is checksummed before and after grading.

## Gates (numeric pass rules)

The judge runs the page twice (1440x900 and 375x780 viewports) in
headless Chromium (`--enable-unsafe-swiftshader`, `--no-sandbox`), and
once more at 1440x900 for the pixel probes.

### Gate 1 — page & context
- The page loads over HTTP with **zero console errors** and zero
  unhandled rejections (browser-reported).
- For every declared effect the library produces a live WebGPU context
  (`navigator.gpu` adapter + device granted) — recorded per region. This
  is also where which backend actually ran is measured.

### Gate 2 — non-blank rendering (per effect)
- Each declared region's canvas is read back with
  `canvas.toDataURL()` after a settling delay; the per-region pixel
  variance of the RGB channels must exceed **12.0** (on the 0-255
  channel scale, population variance of the combined channels of a
  64x64 downsample) so a flat frame cannot pass; and the count of
  distinct 12-bit colours (top 4 bits per channel) must exceed **20**,
  so a two-tone dither cannot pass.

### Gate 3 — animation (per effect)
- Two consecutive canvas captures **1.0 s apart**; the mean absolute
  pixel difference over the 64x64 downsample must exceed **4.0** out of
  255. A live shader that merely drew one frame and stopped fails here.

### Gate 4 — provenance (the effects are real library exports)
- Every `type` in `artist.json` must be a name reported by the pinned
  library's registry at grade time (imported `shaders/js/registry.js`
  from the sha256-verified tarball, not from the artifact).
- The page must not contain any of its own WebGPU/WGSL/GLSL shader
  code: a scan of `index.html` and any local `*.js`/`*.mjs` it loads
  finds no `//wgsl`, `wgsl` code fences, `createShaderModule`,
  `GPUShaderModule`, `gl_FragColor`, or `fragmentShader` outside the
  pinned bundle. (The bundle lives outside the artifact and is served
  from `/vendor/`.) Inline WGSL in a `.js` file means the effect was
  hand-written, not imported.

### Gate 5 — layout (no overflow)
- At 1440x900 and at 375x780: `document.scrollingElement.scrollWidth`
  must be <= viewport width + 1 px. Each declared region must be
  visible in the layout (bounding box height >= 100 px at 1440px
  viewport and >= 80 px at 375px).
- The hero section must contain a text headline: an `h1` whose
  `clientHeight` is > 0 at both viewports (so a bare canvas doesn't
  count as a hero section).

### Gate 6 — performance floor (recorded, not pass/failed by wall time)
- Frames rendered per second during the probe is measured over a 3 s
  window and recorded in the verdict under `performance.fps`. The gate
  passes when fps >= **2** on SwiftShader CPU (the floor that says the
  frame loop is actually turning over in CI). Real numbers go into
  RECEIPT.md.

### Determinism
- Grade twice with the same `--seed`: the verdict JSON must be
  byte-identical outside the `timing` key. Time-dependent shader output
  is captured at fixed virtual timestamps via Chromium's virtual time
  budget, so the same seed gives the same captures.

## Acceptance oracle

The oracle is the rendered pixel output of the pinned library,
measured by the judge itself:

- **Gates 2 & 3:** numeric thresholds on the judge's own pixel
  captures. A blank/static/dithered canvas fails them regardless of
  what the manifest claims.
- **Gate 4:** the sha256-verified local copy of the library's own
  registry ("is this effect a real export?") plus a static scan that
  the page itself contains no shader code.
- **Gate 5:** the browser's own layout metrics at both widths.

Nothing passes because "the page loaded" or "the agent said it was
from the library" — every gate is a measurement the judge takes
itself from the rendered output.

## Backend measurement (recorded, not gated)

Chromium's `--enable-unsafe-swiftshader` gives WebGPU via Dawn's
SwiftShader device when no real GPU exists. The judge records
`adapter.info.vendor`, `adapter.info.architecture`, and
`adapter.info.description` into the verdict's `backend` key so the
receipt shows which path actually rendered the pixels. If WebGPU is
unavailable and the library falls back to WebGL, that is recorded and
Gate 1 fails — the demo grades the WebGPU path only.
