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

## Backend: what works (measured, 2026-10-15)

The library is **WebGPU-only** — there is no WebGL render path in 4.0.4
(the vestigial `context` field in `PresetRendererOptions` is ignored;
`getGPUContext()` always reports `type: "webgpu"`).  In headless
Chromium 150 with `--enable-unsafe-webgpu --enable-unsafe-swiftshader`:

- `navigator.gpu` exists and grants an adapter
  (`vendor=google, architecture=swiftshader`) — **but only in a secure
  context**, so the artifact is always served over HTTP (never
  `data:`/`file:`).
- WebGPU **rasterization works**: a render pass into an offscreen
  `COPY_SRC` texture reads back correct pixels via
  `copyTextureToBuffer` (measured: mean red 255/255 on a test
  triangle).
- WebGPU **canvas presentation does not**: a `webgpu`-context canvas
  stays fully transparent through `drawImage`, `toDataURL`,
  `page.screenshot` and headful (Xvfb) compositing alike — the
  SwiftShader shared-image path to the compositor is broken.  The
  canvas texture itself cannot be used as a copy source either.

So the judge mounts each effect with the library's framework-free
`createRendererFromJSON` (`shaders/core`) and reads the rendered frame
through a small, judge-side WebGPU shim injected before the bundle
loads:

- `GPUCanvasContext.prototype.getCurrentTexture` is wrapped to return a
  judge-owned `RENDER_ATTACHMENT | COPY_SRC` texture of the canvas
  size.  The library's own render pass then draws into it — the pixels
  measured are bytes the library's WGSL pipeline produced; the shim
  only replaces *which texture* the frame lands on (the thing the
  canvas would have presented, had presentation worked).
- `renderFrame({deltaSeconds})` gives frame-locked, deterministic
  rendering: the shader clock advances by exactly the requested
  seconds per call, so a fixed capture schedule reproduces identical
  pixels across runs and machines.

The verdict JSON records the WebGPU probe (`backend.probe.adapter`,
renderer strings) and that grading ran through the texture-readback
shim (`backend.readback: "copyTextureToBuffer"`).

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
    { "type": "Plasma",        "region": "hero-plasma",
      "props": { "speed": 1.0 } }
  ]
}
```

`type` must be an effect name from the pinned library's registry;
`region` must be the `id` of an element in `index.html` containing
exactly one `<canvas>`; `props` is optional and is passed verbatim as
the library component's `props`. The judge serves the artifact verbatim
over HTTP, mounts each declared effect onto its region's canvas from
the **sha256-verified local library copy** (never from any file the
artifact ships), and grades the rendered pixels.

Mounting uses `createRendererFromJSON` from `shaders/core` with the
readback shim described above. Anything else in the page (headings,
copy, buttons, CSS) is fair game. The artifact is graded in a scratch
copy; `judge/` is sha256-checksummed before and after.

## Gates (numeric pass rules)

The judge runs headless Chromium
(`--enable-unsafe-webgpu --enable-unsafe-swiftshader --no-sandbox`) at
1440x900 (layout + pixel probes) and 375x780 (layout probe).

### Gate 1 — page & probes
- The page loads over HTTP with **zero browser-reported console errors**
  and zero unhandled rejections.
- For every declared effect, `createRendererFromJSON(preset)` +
  `initialize(canvas)` resolves without throwing and
  `getFailureReason()` stays `null` within 30 s.
- The verdict records the WebGPU probe (`adapter granted? vendor/arch?`)
  and the WebGL renderer string for reference.

### Gate 2 — non-blank rendering (per effect)
- After `renderFrame({deltaSeconds: 0.5})` the render target is read
  back through the `COPY_SRC` texture (64x64 downsample). The RGB
  channel **population variance must exceed 12.0** (0-255 scale,
  64x64x3 samples), so a flat frame cannot pass; and the number of
  distinct 12-bit colours (top 4 bits per channel) must exceed **20**,
  so a two-tone dither cannot pass.

### Gate 3 — animation (per effect)
- A second deterministic capture one shader-second later
  (`renderFrame({deltaSeconds: 1.0})`); the **mean absolute pixel
  difference between the two captures must exceed 4.0** out of 255 over
  the 64x64 downsample. A shader that drew one frame and stopped fails
  here.

### Gate 4 — provenance (real library exports, no hand-written shaders)
- Every `type` in `artist.json` is a name exported by the pinned
  library's registry (`dist/registry.js` from the sha256-verified
  tarball).
- A static scan of `index.html` and every local `*.js`/`*.mjs` the page
  loads finds no user-authored shader code: none of the tokens
  `createShaderModule`, `GPUShaderModule`, `wgsl`, `gl_FragColor`,
  `fragmentShader`, `vertexShader`. The pinned library is served from
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
- Per effect, the wall time of `renderFrame({deltaSeconds})` calls is
  measured at the region's real canvas size; the gate passes when the
  **mean frame time is <= 20 s/frame** on SwiftShader (≈15–30 s total
  per effect) — a floor that catches pathological hangs, not a speed
  claim. Measured numbers are written to the verdict under
  `performance` and to RECEIPT.md.

### Determinism
- The verdict JSON contains no wall-time fields outside `timing`.
  Two runs with the same `--seed` must produce byte-identical verdict
  JSON outside the `timing` key. Rendering is frame-locked
  (`renderFrame({deltaSeconds})` advances the shader clock by exactly
  the requested amount — verified byte-identical across browser
  launches), so the pixel captures and every derived metric are
  reproducible at a fixed seed.

## Acceptance oracle

The oracle is the rendered pixel output of the pinned library,
measured by the judge itself:

- **Gates 2 & 3:** numeric thresholds on the judge's own pixel
  captures (the real library render pass drawn into the judge's
  `COPY_SRC` texture). A blank / static / two-tone canvas fails them
  regardless of what the manifest claims.
- **Gate 4:** the sha256-verified local copy of the library's own
  registry decides what counts as a real export; a static scan decides
  whether the page ships its own shader code.
- **Gate 5:** the browser's own layout metrics at both widths.

Nothing passes because "the page loaded" or "the agent said it was
from the library" — every gate is a measurement the judge takes itself
from the rendered output.
