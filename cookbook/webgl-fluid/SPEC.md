# SPEC: WebGL fluid simulation, customised and graded headless (CPU WebGL)

## Goal

Show an agent working on a real, popular open-source project inside a
disposable agent-next sandbox: [PavelDoGreat/WebGL-Fluid-Simulation]
(https://github.com/PavelDoGreat/WebGL-Fluid-Simulation) (MIT), pinned at
commit `a2d292931f19d9b3b9f564e23e6c32729d2121c3` (2024-11-12). The sim runs
end to end in headless Chromium on CPU WebGL (SwiftShader, no GPU). The
user's agent *customises* the sim — it adds solid obstacles via a small GLSL
patch and scripts a deterministic dye show (fixed dt, fixed colours, no
real-time clock) — and an independent judge decides, from the GPU dye
texture alone, whether the physics-ish behaviour is right.

The judge never trusts the artifact's own numbers: it loads the artifact in
its own harness, drives it through the artifact's declared script, reads the
dye pixels itself, and compares them against the artifact's declared intent
plus fixed numeric rules below.

## Non-goals

- Real-time / interactive use; 60 fps; audio.
- GPU rendering, extensions beyond core WebGL2 + float color buffers.
- Obstacles other than axis-aligned rectangles in normalized [0,1] coords.
- Any upstream commit other than the pinned SHA above.
- Matching upstream's default visuals (bloom/sunrays/shading are disabled by
  the harness baseline to keep pixel checks exact).

## The harness (judge side, fixed)

`judge/driver/index.html` + `judge/driver/engine.js` load upstream's
`dat.gui.min.js` and `script.js` (fetched at the pinned SHA by
`judge/setup.sh`, sha256-verified at every grade) with:

- `requestAnimationFrame` stubbed to a no-op **before** `script.js` loads,
  so upstream's own `update()` loop runs exactly once with dt = 0 and never
  again — nothing wall-clock-driven can run;
- a hidden fixed-size canvas (`960x540` CSS, `devicePixelRatio` 1);
- a console/onerror/unhandledrejection recorder installed first.

`engine.js` then exposes `window.__WFS__` to the artifact:

| API | what it does |
|---|---|
| `ready()` | resolves after `scene/config.json` is applied onto upstream `config` and framebuffers are re-initialised |
| `scene()` | the parsed artifact config.json |
| `setMaskProgram(fragSrc)` | compiles the artifact's obstacle fragment shader against upstream's `baseVertexShader`; a compile/link failure is recorded as a console error **and** makes every later `frame()` throw |
| `splat(x, y, dx, dy, rgb)` | upstream `splat()`; x,y in [0,1] texcoords (y up), dx,dy velocity in texels/s, rgb in [0,1] |
| `frame(dt)` | `step(dt)` then, if a mask program is set, blits it over dye and velocity (the obstacle enforcement) |
| `capture()` | blits `dye.read` into an RGBA8 FBO via upstream's `copyProgram`, `readPixels` it, and returns `{sha256, mass, cx, cy, nonblank, nan, raw}` of that frame |
| `finish()` | marks the run complete |
| `resetAll()` | zero-fills every FBO and clears the frame log (used between determinism runs) |

Per frame the engine records `sha256` (WebCrypto SHA-256 of the RGBA bytes),
`mass` (sum of mean channel value / 255 over all pixels), intensity-weighted
centroid `(cx, cy)` in normalized coords (y up, matching splat args), and a
NaN flag from a float `readPixels` of the live dye texture when the
implementation supports it.

`judge/run_scene.cjs` (Playwright, headless Chromium, `--use-angle=swiftshader
--enable-unsafe-swiftshader`) loads the harness over `http://127.0.0.1:<port>`
serving `script.js`, `dat.gui.min.js` and the artifact under `scene/`, injects
`scene/drive.js`, and runs the **whole scene twice** (engine `resetAll()`
between runs) for the determinism gate. It returns one JSON blob (console
errors, both runs' per-frame metrics, SSIM between runs when hashes differ,
requested raw frames for media). `judge/check_gates.py` computes every gate
from that blob plus the artifact's `config.json`; nothing in the verdict comes
from the artifact's own code.

## Artifact

A directory with exactly three files:

```
<artifact>/
├── config.json     # the scene: dt, upstream config overrides, scripted
│                   # splats, the probe, the obstacles, the aim splat
├── drive.js        # the driver script: deterministic loop that calls the
│                   # harness API (splats at scripted frames, mask program,
│                   # fixed dt, N frames, finish())
└── obstacle.frag   # the agent's GLSL patch: fragment shader that zeroes
                    # dye and velocity inside the obstacle rectangles
```

`config.json` must contain, with the exact key names the judge reads:

- `dt` (fixed timestep, s), `frames` (total frames stepped),
- `config`: upstream overrides — must keep `SHADING`, `BLOOM`, `SUNRAYS`,
  `COLORFUL` false (pixel checks) — may set `SIM_RESOLUTION` (64..128),
  `DYE_RESOLUTION` (128..256), `DENSITY_DISSIPATION` (0.5..2.0, default
  1.0), `VELOCITY_DISSIPATION`, `PRESSURE`, `PRESSURE_ITERATIONS`,
  `CURL`, `SPLAT_RADIUS`, `SPLAT_FORCE`;
- `probe`: one calibration splat fired alone at frame `probe.frame` with
  velocity `(dx, dy)`, declaring `trackFrames`;
- `obstacles`: axis-aligned rects `{x0, y0, x1, y1}` in normalized coords
  (y up, same convention as splats), non-empty;
- `aim`: one splat fired at the obstacles from outside them;
- `show`: the decorative scripted splat sequence (frames, positions,
  velocities, colours — "spelling" a shape).

## Gates (numeric pass rules)

All gates run on the judge's own readback of the dye texture. `m[k]` is the
mass of frame k, `c[k] = (cx, cy)` its centroid, in normalized coords, y up.

1. **Loads clean.** Zero console errors and zero uncaught errors/rejections
   across both runs; both runs complete exactly `frames` frames; WebGL2
   context created (renderer string recorded in the verdict).
2. **Deterministic.** For every frame index, run 1 and run 2 have identical
   SHA-256 hashes. If SwiftShader proves nondeterministic on the grading
   host, the gate instead passes on mean SSIM >= 0.99 across frames —
   whichever branch fired is recorded in the verdict (`hash_equal`), and a
   Deviation is logged in RECEIPT.md.
3. **Dye is advected by its velocity.** Over frames `p = probe.frame` (the
   first captured frame after the probe splat) to `p + probe.trackFrames`:
   displacement `d = c[p + trackFrames] - c[p]` must satisfy
   `dot(d, v)/|d||v| >= cos(60 deg)` (direction within 60° of the declared
   probe velocity `v = (dx, dy)`), `|d| >= 0.02` (moved, in normalized
   units), and `dot(c[k+6] - c[k], v_hat) > 0` for every k in the window
   (progress is forward, never backwards, at 6-frame granularity).
4. **Obstacles respected.** At every frame from `aim.frame + 8` to the last
   frame, the dye mass inside each declared obstacle rectangle is
   `<= 0.5%` of that frame's total mass. (The judge computes the rectangle
   mask itself from `config.json`; the artifact's shader enforcement is what
   must keep it clean.)
5. **Dye dissipates as configured.** Over the probe window
   (`p` to `p + trackFrames`, no splats inside): every step
   `m[k+1] <= 1.001 * m[k]` (monotone within quantization noise), and the
   measured per-frame decay `(m[p+track]/m[p])^(1/track)` lies within
   `[0.75, 1.25]` of the configured `exp(-dt * DENSITY_DISSIPATION)`.
6. **No NaN, no blank frames.** Every captured frame in both runs:
   `mass >= 0.5` (not blank) and `nan == false` (no non-finite value in the
   float dye readback; when the implementation cannot read floats, the
   verdict says so and this gate additionally requires every frame to have
   `mass >= 0.5` and `nonblank >= 100` pixels).

`judge/grade.sh <artifact> [--seed N] [--json out.json] [--keep-frames DIR]`
copies the artifact to a scratch dir, checksums `judge/` before and after,
runs the two scene runs, evaluates the six gates, prints one JSON verdict,
exits 0 only if all gates pass. `--keep-frames DIR` additionally writes real
PNGs of chosen frames for `media/` (RGBA buffers captured by the engine,
encoded by the judge with stdlib Python).

## Acceptance oracle

- Gate 3's oracle is the artifact's *own declared* probe velocity direction —
  a sim whose dye drifts against its velocity field, or sits still, fails.
- Gate 4's oracle is the artifact's *own declared* obstacle rectangles — a
  mask the sim does not enforce (mutant: mask program never installed) fails.
- Gate 5's oracle is the closed-form dissipation law built into upstream's
  own shaders (`value / (1.0 + dt * decay)` ≈ `exp(-dt*decay)` per frame)
  applied to the configured `DENSITY_DISSIPATION` — decay too slow
  (dissipation patched to 0) or mass that grows fails.
- Gate 2's oracle is bit-level identity of the rendered frames; gate 1 and 6
  are load-time contracts (zero console errors; finite, non-empty dye).

Nothing passes because "the sim ran" — every gate compares judge-measured
pixels against a number with an independent source.

## Self-test (mandatory)

`judge/selftest.sh` grades the known-good artifact (must pass), re-grades it
with the same seed (verdict JSON must be byte-identical outside `timing`),
and grades every mutant generated by `judge/mutants.py` from the good one.
Kill rate must be >= 90%; each mutant is a single edit of the good artifact:

| mutant | edit | must fail |
|---|---|---|
| `velocity_flip` | probe `dy` sign flipped in `drive.js` | gate 3 |
| `obstacles_ignored` | `setMaskProgram` call removed from `drive.js` | gate 4 |
| `dissipation_zero` | `config.DENSITY_DISSIPATION` set to 0 in `config.json` | gate 5 |
| `nan_inject` | one splat given a NaN velocity in `drive.js` | gate 6 |
| `broken_shader` | syntax error introduced in `obstacle.frag` | gate 1 |

## Performance envelope

Everything must run headless on 2 vCPU / ~3 GB RAM: the good scene is
`SIM_RESOLUTION` 128, `DYE_RESOLUTION` 256 (dye FBO 455x256), effects off,
84 frames per run, 2 runs per grade. One grade < 4 min on 2 vCPU.
