# SPEC: Shaders Gallery (WebGPU shader hero sections in headless Chromium)

## Goal

Demonstrate an agent-next sandbox composing a hero section from the
popular open-source **shaders** component library
(<https://github.com/shader-effects-inc/shaders> — the npm package
`shaders`, ~4.8k GitHub stars, 200+ shader effect components), rendered
headless in the sandbox in Chromium, and graded by an independent judge
that checks the rendered pixels, not the agent's claims.

- Upstream package: `shaders` on npm, **pinned to version 4.0.4**
  (2026-10-09), sha256-verified at setup time. MIT licence by
  Shader Effects Inc.; a copy of the licence ships in the good example.
- Headless Chromium 150.0.7871.100 (Debian bookworm, pinned +
  sha256-verified) renders the page. 2 vCPU / ~4 GB RAM is enough.

## Backend: which works (measured, 2026-10-15)

Chromium 150 can grant a WebGPU adapter in headless software mode
(`--enable-unsafe-webgpu --enable-unsafe-swiftshader`: adapter granted,
`vendor=google, architecture=swiftshader`) — but **SwiftShader's WebGPU
draw path does not rasterize**: the registry reports `supported`, the
device is granted, every `createShader` call resolves, zero console
errors are raised, and yet every canvas stays fully transparent on
readback (64x64 downsample variance 0, distinct-colour count 1, on
Aurora / Blob / ConicGradient alike). Screenshots of the page confirm
nothing is drawn.

The same Chromium build's **WebGL2 path over the same SwiftShader
driver rasterizes correctly** (`WEBGL_debug_renderer_info` reports
`ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero)))` and test
triangles render with real pixel variance).

So this demo grades the library's rendered output through **WebGL2 on
SwiftShader**, which is the fallback the library's docs describe for
environments without a working GPU; the verdict JSON records both which
backend rendered and what the WebGPU probe found
(`backend.probe.adapter`, `backend.probe.swiftshaderBlank`). On a
machine with a working WebGPU rasterizer the same gates run unchanged.

## Non-goals

- The React/Vue/Svelte/Solid bindings, the partner bundle,
  `npx shaders` tooling, MCP servers, building the library from source.
  The sha256-verified npm tarball is the only source of library code,
  and only the framework-free `shaders/js` entry is used.
- Native-GPU WebGPU, multiple effects layered on one canvas, custom
  user-authored WGSL, video encoding (that is the media task's job).

## Artifact

One **artifact directory** — a static hero-section page plus a
manifest:

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
    { "type": "Aurora",        "region": "hero-aurora" },
    { "type": "Blob",          "region": "hero-blob" },
    { "type": "ConicGradient", "region": "hero-conic" }
  ]
}
```

`type` must be an effect name from the pinned library's registry;
`region` must be the `id` of an element in `index.html` containing
exactly one `<canvas>`. The judge serves the artifact verbatim over
HTTP, mounts each declared effect onto its region's canvas from the
**sha256-verified local library bundle** (never from any copy the
artifact ships), and grades the rendered pixels.

The judge renders with the WebGL rasterizer (`context` option of
`createShader` — the library's documented fallback), after recording
the WebGPU probe results described above. Anything else in the page
(headings, copy, buttons, CSS) is fair game. The artifact is graded in
a scratch copy; `judge/` is sha256-checksummed before and after.

## Gates (numeric pass rules)

The judge runs headless Chromium
(`--enable-unsafe-webgpu --enable-unsafe-swiftshader --no-sandbox`) at
1440x900 (layout + pixel probes) and 375x780 (layout probe).

### Gate 1 — page & probes
- The page loads over HTTP with **zero browser-reported console errors**
  and zero unhandled rejections.
- For every declared effect, mounting the library component on the
  region's canvas resolves without throwing and without an
  `onError` callback within 30 s; the mount is recorded with the
  backend actually used (`webgl`).
- The verdict records the WebGPU probe (`adapter granted? vendor/arch?`)
  and the WebGL renderer string.

### Gate 2 — non-blank rendering (per effect)
- Each declared region's canvas is read back
  (`canvas.toDataURL()` into a 64x64 downsample). The RGB channel
  **population variance must exceed 12.0** (0-255 scale, 64x64x3
  samples), so a flat frame cannot pass; and the number of distinct
  12-bit colours (top 4 bits per channel) must exceed **20**, so a
  two-tone dither cannot pass.

### Gate 3 — animation (per effect)
- Two captures of the canvas 1.0 s apart; the **mean absolute pixel
  difference must exceed 4.0** out of 255 over the 64x64 downsample.
  A shader that drew one frame and stopped fails here.

### Gate 4 — provenance (real library exports, no hand-written shaders)
- Every `type` in `artist.json` is a name exported by the pinned
  library's registry (`dist/js/registry.js` from the sha256-verified
  tarball).
- A static scan of `index.html` and every local `*.js`/`*.mjs` the page
  loads finds no user-authored shader code: none of the tokens
  `createShaderModule`, `GPUShaderModule`, `wgsl`, `gl_FragColor`,
  `fragmentShader`, `vertexShader`. The pinned bundle is served from
  `/vendor/` outside the artifact, so inline WGSL/GLSL in the artifact
  means the effect was hand-written, not imported.

### Gate 5 — layout (no overflow)
- At 1440x900 and at 375x780: `document.scrollingElement.scrollWidth <=
  innerWidth + 1 px`.
- Each declared region's bounding box is at least 100 px tall at 1440
  px width and at least 80 px tall at 375 px width.
- The hero section contains a headline: an `h1` with `clientHeight > 0`
  at both widths.

### Gate 6 — performance floor (recorded + minimal threshold)
- Rendered frames per second is measured over a 3 s window per effect
  (rAF callbacks counted). The gate passes when fps >= **2** on
  SwiftShader; measured numbers are written to the verdict under
  `performance` and to RECEIPT.md.

### Determinism
- The verdict JSON contains no wall-time fields outside `timing`.
  Two runs with the same `--seed` must produce byte-identical verdict
  JSON outside the `timing` key. Time-dependent captures are taken at
  fixed offsets after `onReady` (canvas pixels are read with the render
  loop paused at a fixed frame count where the library allows it), so
  shader animation state at capture time is reproducible at a fixed
  seed.

## Acceptance oracle

The oracle is the rendered pixel output of the pinned library,
measured by the judge itself:

- **Gates 2 & 3:** numeric thresholds on the judge's own pixel
  captures. A blank / static / two-tone canvas fails them regardless of
  what the manifest claims.
- **Gate 4:** the sha256-verified local copy of the library's own
  registry decides what counts as a real export; a static scan decides
  whether the page ships its own shader code.
- **Gate 5:** the browser's own layout metrics at both widths.

Nothing passes because "the page loaded" or "the agent said it was
from the library" — every gate is a measurement the judge takes itself
from the rendered output.
