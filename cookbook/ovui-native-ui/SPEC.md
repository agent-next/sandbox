# SPEC: ovui native tool panel (NVIDIA Omniverse `ovui`, headless Vulkan/lavapipe)

## Goal

Demonstrate an agent building a small **native 3D-tool UI panel** with
[NVIDIA Omniverse `ovui`](https://github.com/NVIDIA-Omniverse/ovui) (pip
`ovui`, Apache-2.0) inside a CPU-only agent-next sandbox, rendered
**headless** through ovui's Vulkan offscreen backend on Mesa lavapipe (CPU
renderer; no GPU, no display). A pixel- and model-level judge the agent
cannot fool checks the rendered panel against a fixed UI spec.

ovui headless mode (`OMNIUI_HEADLESS=1`) renders through its real
ImGui/Vulkan stack, so a headless screenshot is pixel-identical to a
display-connected run of the same software version; on a CPU-only host the
Vulkan device is Mesa lavapipe.

## Spec for the artifact (fixed)

The panel the agent must build is fixed in every structural detail:

| element | requirement |
|---|---|
| window | `ui.Window` titled `Tool Panel`, `width=420`, `height=360` |
| body layout | the widgets below, inside a single `ui.VStack` in the window's frame, in this top-to-bottom order: sliders, swatch, checkbox, button |
| sliders | exactly 3 `ui.FloatSlider` widgets, each in its own fixed-width `ui.HStack` row (`width = 300 px`) beside a `ui.Label` (`S1`, `S2`, `S3`, `width = 32 px`) |
| slider 1 | `min = 0.0`, `max = 10.0`, label `S1` |
| slider 2 | `min = 0.0`, `max = 20.0`, label `S2` |
| slider 3 | `min = 0.0`, `max = 50.0`, label `S3` |
| color swatch | exactly 1 `ui.ColorWidget`, constant color rgba `(0.2, 0.5, 0.9, 1.0)`, `width = 140 px`, `height = 24 px` |
| checkbox | exactly 1 `ui.CheckBox` |
| button | exactly 1 `ui.Button` with visible text `Apply` |

Model **values** (slider values, checkbox state, callback behaviour) are
the agent's free choice; widget types, ranges, the swatch color/size and
the window title are not.

## Non-goals

- Interactive editing, scene manipulators, or the `omni.ui.scene` 3D
  viewport.
- Any GPU/CUDA path: the demo must prove CPU-only works (the agent sandbox
  has no `libcuda.so.1`; the judge installs the stub documented in
  `judge/setup.sh`, and ovui falls back to its Vulkan/lavapipe path).
- Fonts/DPI variants, multiple panel designs, animations: one settled
  frame is the artifact.
- ovui features beyond the widget types above.

## Artifact

One Python file, `panel.py`, importable without side effects, defining

```python
def build_panel() -> tuple["omni.ui.Window", dict]:
    ...
```

It builds the spec panel and returns `(window, refs)` where `refs` maps
exactly these names to the **widget objects** the builder created:
`window` (the `ui.Window`), `slider1`, `slider2`, `slider3` (the three
`ui.FloatSlider`, in spec order), `checkbox`, `button`, `swatch`. The
judge reads widget geometry, ranges and the swatch color directly from
these live objects via ovui's API, and renders via a harness
(`judge/render.py`) the artifact cannot modify. Known-good:
`examples/good/panel.py`.

The artifact may import only `omni.ui` (and its submodules), `numpy`, and
the Python standard library.

## Gates (numeric pass rules)

`judge/grade.sh <panel.py> [--json out.json]` runs every gate in a scratch
copy of the artifact and exits 0 only if every gate passes.

- **Gate 0 — runs and renders.** `judge/render.py panel.py out.png
  tree.json` imports the artifact, calls `build_panel()`, settles 9
  frames, and saves a screenshot, all inside a 90 s wall limit; exit 0,
  `out.png` is a valid PNG of at least the window size.
- **Gate 1 — widget objects.** From the returned `refs`:
  - `refs["window"]` is a `ui.Window` with `title == "Tool Panel"`,
    `computed` canvas >= 420 x 360;
  - `refs["slider1".."3"]` are exactly three distinct `ui.FloatSlider`
    instances with `(min, max)` equal to `(0,10)`, `(0,20)`, `(0,50)`
    respectively (within 1e-6);
  - `refs["checkbox"]` is a `ui.CheckBox`, `refs["button"]` is a
    `ui.Button` with non-empty text containing `Apply`;
  - `refs["swatch"]` is a `ui.ColorWidget` with `computed_width == 140 ±
    2` and `computed_height == 24 ± 2`, and its colour model's first three
    components `(r, g, b)` equal `(0.2, 0.5, 0.9)` within 1e-6.
- **Gate 2 — pixel spec mask.** The judge crops the screenshot to the
  window's content rect (the window's own screen position and computed
  size inset by its `padding_x`/`padding_y`), and checks:
  - every required widget's screen rect lies fully inside the window
    content region with margin >= 0 (no overflow/clipping);
  - swatch: median RGB over the swatch rect (inset 3 px) matches the
    target in `judge/reference.json` (the known-good example's own
    rendered median, with the known-good's 3-render jitter) to within a
    fixed per-channel band of `max(12, 4 * jitter)`;
  - each slider, the checkbox and the button rect (each inset 2 px) is
    *drawn*: its luminance variance exceeds the window-background variance
    in an equally sized empty region by >= 8 (0..255 scale);
  - the title text region (the window title bar band) is brighter/darker
    than the body background by luminance delta >= 20 somewhere in the
    band (text is rendered);
  - the button `Apply` text renders: the button rect contains >= 25
    pixels whose luminance differs from the button-background luminance by
    >= 30.
- **Gate 3 — determinism.** The judge renders the artifact a second time
  in a fresh process; the two cropped screenshots must be byte-identical.
  A baked-PNG artifact fails Gate 1 (no live widgets); nondeterministic
  rendering fails this gate.

## Acceptance oracle

Nothing passes because "the script ran":

- Gate 1 compares live widget objects returned by the artifact's own
  builder against the fixed spec table — widget types, slider ranges,
  swatch size and the swatch colour read from the widget's colour model.
- Gate 2 compares rendered pixels in explicit spec regions against the
  spec mask; the swatch target comes from the known-good render plus its
  measured render jitter (`judge/reference.json`, see RECEIPT) — an
  independent reference, not the artifact's claim.
- Gate 3 needs a fresh process to reproduce the render bit-for-bit, so
  output-caching or environment-spoofing fails.

## Determinism

The Vulkan/lavapipe render is deterministic for a fixed ovui version,
fixed window geometry and a fixed settled frame count (the harness settles
9 frames). `judge/grade.sh` run twice with the same `--seed` produces
byte-identical verdict JSON except the `timing` key; `judge/selftest.sh`
checks this.
